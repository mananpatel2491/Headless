"""Unit tests for headless/report.py: the self-contained HTML report
generator (spec 005-insurance-quote-comparison, User Story 3, research.md
D6, contracts/walk-capture-report.md section 5, T031-T032b).
"""

from __future__ import annotations

import re
import stat

from headless.capture import CurrentPolicy, QuoteCapture
from headless.compare import build_comparison
from headless.report import render_exclusion_report, render_report, write_report

_EXTERNAL_REF_RE = re.compile(r'https?://|<script src=|<link rel="stylesheet" href=')


def _current_policy() -> CurrentPolicy:
    return CurrentPolicy(
        insurer="Current Insurer",
        premium={"term_months": "6", "amount": "600.00"},
        coverages=[{"line": "Collision", "limit": "500", "deductible": "500", "premium": ""}],
    )


def _quote(insurer: str, **overrides) -> QuoteCapture:
    base = dict(
        insurer=insurer,
        fetched_at="2026-08-26T12:00:00+00:00",
        premium={"term_months": "6", "amount": "500.00"},
        coverages=[{"line": "collision", "limit": "1000", "deductible": "500", "premium": ""}],
        source_url="https://example.com/quote",
        package="standard",
    )
    base.update(overrides)
    return QuoteCapture(**base)


# --- T031: report structure --------------------------------------------


def test_report_has_one_column_per_quote_plus_current_policy():
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "<th>Current Policy</th>" in html
    assert "<th>progressive</th>" in html


def test_report_marks_a_better_cell_and_a_premium_row():
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "mark-better" in html
    assert "Premium" in html


def test_report_premium_row_labels_the_current_premiums_own_term():
    # FIX-FIRST 4 (Opus verifier, 2026-08-26): the current-policy premium
    # cell must never show a bare N-month figure beside a monthly one - it
    # carries its own term label plus the same monthly-equivalent
    # computation every quote's own cell already uses.
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "600.00 per 6 months" in html
    assert "100.00/mo equivalent" in html


def test_report_recommendation_banner_names_the_top_quote_and_rule_trail():
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "Recommended: progressive" in html
    assert comparison.rule_trail in html


def test_report_with_no_recommendation_renders_a_plain_statement_not_a_broken_banner():
    comparison = build_comparison(_current_policy(), {})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "No comparison exists yet" in html
    assert "Recommended:" not in html


# --- T032: zero-external-reference, value-free failure row, provenance -----


def test_report_has_zero_external_references_outside_the_footer_source_url():
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=_current_policy())

    matches = list(_EXTERNAL_REF_RE.finditer(html))
    # The only allowed match is the plain-text source_url in the footer.
    for match in matches:
        # Confirm every match is inside the footer's provenance <li>, not a
        # <script src=/<link ...> tag anywhere else in the document.
        assert match.group(0).startswith("https://") or match.group(0).startswith("http://")
    assert "<script src=" not in html
    assert '<link rel="stylesheet" href=' not in html


def test_report_never_leaks_a_distinctive_failure_string_only_the_fixed_phrase():
    comparison = build_comparison(_current_policy(), {})
    distinctive = "DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR"
    failed = ["progressive"]  # the report never receives distinctive itself - it is fixed by design
    html = render_report(comparison, [], failed, current_policy=_current_policy())
    assert distinctive not in html
    assert "no successful capture yet" in html
    assert "progressive" in html


def test_report_provenance_footer_names_fetched_at_and_source_url_only():
    quote = _quote("progressive", fetched_at="2026-08-26T09:00:00+00:00", source_url="https://progressive.example/quote/1")
    comparison = build_comparison(_current_policy(), {"progressive": quote})
    html = render_report(comparison, [], [], current_policy=_current_policy())
    assert "2026-08-26T09:00:00+00:00" in html
    assert "https://progressive.example/quote/1" in html
    assert "standard" in html  # package, when present
    # No premium/coverage figure is duplicated in the footer beyond the table.
    footer = html.split("<footer>", 1)[1]
    assert "$1000" not in footer  # the raw captured limit is never repeated in the footer


def test_report_unmapped_and_failed_rows_state_only_id_and_fixed_phrase():
    comparison = build_comparison(_current_policy(), {})
    html = render_report(comparison, ["geico"], ["allstate"], current_policy=_current_policy())
    assert "geico" in html and "not mapped yet" in html
    assert "allstate" in html and "no successful capture yet" in html


# --- T032b: no-current-policy report -----------------------------------


def test_no_current_policy_report_shows_marker_in_every_current_policy_row():
    comparison = build_comparison(None, {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=None)
    assert "no current-policy reference for vehicles.primary - run scripts/policy_extract.py" in html


def test_no_current_policy_report_has_no_better_worse_marks():
    # The legend's own fixed CSS classes always show in the <style> block
    # and its <span> legend (a static, always-present key); what must never
    # appear is a *table cell* actually carrying one of these classes,
    # since no classification is computed at all in this branch
    # (ComparisonResult.has_current_policy is False). Scope the check to
    # the <table>...</table> region only, excluding the legend above it.
    comparison = build_comparison(None, {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=None)
    table_html = html.split("<table>", 1)[1].split("</table>", 1)[0]
    for cls in ("mark-better", "mark-worse", "mark-equal", "mark-missing", "mark-not-comparable"):
        assert f'class="{cls}"' not in table_html


def test_no_current_policy_rule_trail_names_premium_only_ranking():
    comparison = build_comparison(None, {"progressive": _quote("progressive")})
    html = render_report(comparison, [], [], current_policy=None)
    assert "no current-policy reference on file" in html


# --- HTML escaping of untrusted captured text -------------------------------


def test_captured_text_is_escaped_before_reaching_the_output():
    hostile_quote = _quote(
        "progressive",
        coverages=[{"line": "<script>alert(1)</script>", "limit": "<img src=x>", "deductible": "", "premium": ""}],
    )
    comparison = build_comparison(None, {"progressive": hostile_quote})
    html = render_report(comparison, [], [], current_policy=None)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x>" not in html
    assert "&lt;script&gt;" in html or "&lt;img" in html


# --- write_report -------------------------------------------------------


# --- provenance footer: generator/converter (spec 006-policy-extraction-v2, FR-024) ---


def test_footer_renders_generator_and_converter_when_present():
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(
        comparison,
        [],
        [],
        current_policy=_current_policy(),
        current_policy_source="/tmp/example-policy.pdf",
        current_policy_confirmed_at="2026-08-29T00:00:00+00:00",
        current_policy_generator="local-llm:qwen3.5:35b",
        current_policy_converter="pymupdf4llm",
    )
    assert "local-llm:qwen3.5:35b" in html
    assert "pymupdf4llm" in html


def test_footer_degrades_to_the_v005_shape_when_generator_and_converter_are_absent():
    # A cache file written before spec 006 existed has no
    # generator/converter fields at all (data-model.md's own additive-only
    # invariant) - the footer must render exactly as v0.0.5 already did,
    # never a broken or partially-labelled line.
    comparison = build_comparison(_current_policy(), {"progressive": _quote("progressive")})
    html = render_report(
        comparison,
        [],
        [],
        current_policy=_current_policy(),
        current_policy_source="/tmp/example-policy.pdf",
        current_policy_confirmed_at="2026-08-29T00:00:00+00:00",
    )
    footer_line = [line for line in html.splitlines() if "Current-policy reference" in line][0]
    assert "generator" not in footer_line
    assert "converter" not in footer_line
    assert "/tmp/example-policy.pdf" in footer_line
    assert "2026-08-29T00:00:00+00:00" in footer_line


def test_write_report_writes_dated_file_and_overwrites_same_date(tmp_path):
    html_first = "<html>first</html>"
    path_first = write_report(html_first, tmp_path)
    assert path_first.exists()
    assert path_first.name.startswith("quote-comparison-")
    assert path_first.read_text(encoding="utf-8") == html_first

    html_second = "<html>second</html>"
    path_second = write_report(html_second, tmp_path)
    assert path_second == path_first
    assert path_second.read_text(encoding="utf-8") == html_second


def test_write_report_writes_at_mode_0600_including_on_a_same_date_overwrite(tmp_path):
    # NIT 6 (Opus verifier, 2026-08-26): reports/ is vault-grade local data
    # - the report must land at 0600 from creation, not write-then-chmod,
    # and stay 0600 across a same-UTC-date overwrite too.
    path_first = write_report("<html>first</html>", tmp_path)
    assert stat.S_IMODE(path_first.stat().st_mode) == 0o600

    path_first.chmod(0o644)  # simulate a looser mode from an earlier write
    path_second = write_report("<html>second</html>", tmp_path)
    assert stat.S_IMODE(path_second.stat().st_mode) == 0o600


def test_render_exclusion_report_states_the_exclusion_plainly():
    html = render_exclusion_report("vehicles.primary")
    assert "vehicles.primary excluded by profile (n/a)" in html
    assert "<table>" not in html  # no comparison table, per FR-064
