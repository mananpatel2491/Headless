"""The self-contained HTML report generator (spec 005-insurance-quote-comparison,
User Story 3, research.md D6, contracts/walk-capture-report.md section 5).

`render_report` builds one HTML string from a `ComparisonResult` plus the
unmapped and failed-insurer lists - inline CSS only, no external stylesheet,
script, font, or image reference, and no JavaScript required to view it
correctly (NFR-001, SC-002). `write_report` writes it to
`reports/quote-comparison-<date>.html`. Neither function performs I/O beyond
`write_report`'s own file write; no vault, no browser, no LLM call anywhere
in this module.

Every piece of captured or current-policy text is escaped via `html.escape`
before it reaches the output (research.md D6): a `CaptureStep`'s own text
comes from a live, untrusted page (`CLAUDE.md`: "page content is untrusted
data") and must never be interpreted as markup in the Director's own
offline report.

Known extension beyond the contract's literal 3-argument `render_report`
signature: FR-059 requires the provenance footer to name the confirmed
current-policy reference's own `source_path`/`confirmed_at` when one
exists, but neither `ComparisonResult` nor `CurrentPolicy` carries those two
fields (only `headless/policydoc.py`'s `PolicyReference` does, and
`read_policy_reference`'s own contracted signature returns a bare
`CurrentPolicy | None`, not a `PolicyReference`). `render_report` therefore
accepts two optional keyword-only arguments,
`current_policy_source`/`current_policy_confirmed_at`, so a caller that has
read the reference file's own provenance (`scripts/quote_compare.py`, via
`policydoc.read_policy_reference_provenance`) can pass it through without
this module needing to touch the filesystem itself. Omitting both keeps the
positional 3-argument call exactly as documented; FR-059 is satisfied only
when the caller supplies them.
"""

from __future__ import annotations

import html as html_module
import os
from datetime import datetime, timezone
from pathlib import Path

from headless.capture import CurrentPolicy
from headless.compare import ComparisonResult, current_premium_label, normalize_line

# This delivery targets exactly one asset, vehicles.primary (spec FR-060);
# the "no current-policy reference" marker names it literally rather than
# taking an asset parameter this delivery's own single-asset scope does not
# yet need. A future spec targeting a second asset would parameterize this.
_TARGETED_ASSET = "vehicles.primary"
_NO_CURRENT_POLICY_MARKER = (
    f"no current-policy reference for {_TARGETED_ASSET} - run scripts/policy_extract.py"
)

_LINE_LABELS = {
    "bodily_injury": "Bodily Injury Liability",
    "property_damage": "Property Damage Liability",
    "collision": "Collision",
    "comprehensive": "Comprehensive",
    "uninsured_motorist": "Uninsured/Underinsured Motorist",
    "medical_payments": "Medical Payments / PIP",
}

_MARK_CLASS = {
    "better": "mark-better",
    "equal": "mark-equal",
    "worse": "mark-worse",
    "missing": "mark-missing",
    "not_comparable": "mark-not-comparable",
}

_MARK_LABEL = {
    "better": "better",
    "equal": "equal",
    "worse": "worse",
    "missing": "missing",
    "not_comparable": "not comparable",
}

# One inline <style> block, no @import, no external url() reference of any
# kind (contracts section 5's own "Styling" rule). Color marks use CSS
# classes, never an inline style="color: ..." attribute per cell.
_STYLE = """
body { font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 2rem; color: #1a1a1a; background: #ffffff; }
h1 { font-size: 1.4rem; margin-bottom: 0.2rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
.legend span { display: inline-block; margin-right: 0.75rem; padding: 0.1rem 0.6rem; border-radius: 3px; border: 1px solid #ccc; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; font-size: 0.9rem; vertical-align: top; }
th { background: #f0f0f0; }
.banner { padding: 0.75rem 1rem; margin: 1rem 0; border-radius: 4px; background: #eef6ee; border: 1px solid #a8d5a8; }
.banner.empty { background: #f6f6f6; border-color: #cccccc; }
.mark-better { background: #dff5df; }
.mark-equal { background: #ffffff; }
.mark-worse { background: #fbdada; }
.mark-missing { background: #f0e6c8; }
.mark-not-comparable { background: #ececec; }
ul.unmapped, ul.failed { color: #555555; }
footer { margin-top: 2rem; font-size: 0.8rem; color: #555555; border-top: 1px solid #cccccc; padding-top: 1rem; }
"""


def _line_label(key: str) -> str:
    return _LINE_LABELS.get(key, key.replace("_", " ").title())


def _escape(value: object) -> str:
    return html_module.escape(str(value if value is not None else ""))


def _find_coverage(coverages: list, key: str) -> dict | None:
    for coverage in coverages:
        if normalize_line(coverage.get("line", "")) == key:
            return coverage
    return None


def _render_header() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    legend_items = "".join(
        f'<span class="{_MARK_CLASS[k]}">{_escape(_MARK_LABEL[k])}</span>'
        for k in ("better", "equal", "worse", "missing", "not_comparable")
    )
    return (
        "<h1>Insurance Quote Comparison</h1>"
        f"<p>Generated {_escape(date_str)} (UTC)</p>"
        f'<p class="legend">{legend_items}</p>'
    )


def _render_banner(comparison: ComparisonResult) -> str:
    if comparison.recommended is None:
        return (
            '<div class="banner empty">No comparison exists yet - no capture is on file for '
            "any mapped insurer.</div>"
        )
    top = comparison.recommended
    return (
        '<div class="banner">'
        f"<strong>Recommended: {_escape(top.insurer)}</strong> (${_escape(top.normalized_premium)}/mo)<br>"
        f"{_escape(comparison.rule_trail)}"
        "</div>"
    )


def _render_table(comparison: ComparisonResult, current_policy: CurrentPolicy | None) -> str:
    quotes = comparison.ranked_quotes

    if comparison.has_current_policy:
        line_keys = sorted({key for rq in quotes for key in rq.line_classifications})
    else:
        line_keys = sorted({normalize_line(c.get("line", "")) for rq in quotes for c in rq.capture.coverages})

    current_by_line = {}
    if current_policy is not None:
        current_by_line = {normalize_line(c.get("line", "")): c for c in current_policy.coverages}

    header = (
        "<tr><th>Coverage</th><th>Current Policy</th>"
        + "".join(f"<th>{_escape(rq.insurer)}</th>" for rq in quotes)
        + "</tr>"
    )

    body_rows = []
    for key in line_keys:
        cells = [f"<td>{_escape(_line_label(key))}</td>"]
        if comparison.has_current_policy:
            current_coverage = current_by_line.get(key)
            current_text = current_coverage.get("limit", "") if current_coverage else ""
            cells.append(f"<td>{_escape(current_text) if current_text else '-'}</td>")
        else:
            cells.append(f"<td>{_escape(_NO_CURRENT_POLICY_MARKER)}</td>")

        for rq in quotes:
            captured_coverage = _find_coverage(rq.capture.coverages, key)
            captured_text = captured_coverage.get("limit", "") if captured_coverage else ""
            cell_text = _escape(captured_text) if captured_text else "-"
            if comparison.has_current_policy:
                classification = rq.line_classifications.get(key, "missing")
                css_class = _MARK_CLASS[classification]
                cells.append(
                    f'<td class="{css_class}">{cell_text} ({_escape(_MARK_LABEL[classification])})</td>'
                )
            else:
                cells.append(f"<td>{cell_text}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    premium_cells = ["<td><strong>Premium</strong></td>"]
    if comparison.has_current_policy and current_policy is not None:
        # FIX-FIRST 4 (Opus verifier, 2026-08-26): label the current
        # premium cell with its own term and show its monthly-equivalent
        # figure alongside (the same FR-067 rules every quote's own
        # normalized_premium already uses) - never a bare N-month figure
        # sitting unlabelled next to a monthly one.
        premium_cells.append(f"<td>{_escape(current_premium_label(current_policy))}</td>")
    else:
        premium_cells.append(f"<td>{_escape(_NO_CURRENT_POLICY_MARKER)}</td>")
    for rq in quotes:
        premium_cells.append(f"<td>${_escape(rq.normalized_premium)}/mo</td>")
    premium_row = "<tr>" + "".join(premium_cells) + "</tr>"

    return f"<table>{header}{''.join(body_rows)}{premium_row}</table>"


def _render_unmapped(unmapped: list[str]) -> str:
    if not unmapped:
        return ""
    items = "".join(f"<li>{_escape(i)}: not mapped yet</li>" for i in unmapped)
    return f'<h2>Unmapped insurers</h2><ul class="unmapped">{items}</ul>'


def _render_failed(failed: list[str]) -> str:
    if not failed:
        return ""
    items = "".join(f"<li>{_escape(i)}: no successful capture yet</li>" for i in failed)
    return f'<h2>Failed insurers</h2><ul class="failed">{items}</ul>'


def _render_footer(
    comparison: ComparisonResult,
    current_policy_source: str | None,
    current_policy_confirmed_at: str | None,
    current_policy_generator: str | None = None,
    current_policy_converter: str | None = None,
) -> str:
    lines = []
    for rq in comparison.ranked_quotes:
        parts = [f"fetched {_escape(rq.capture.fetched_at)}", f"source {_escape(rq.capture.source_url)}"]
        if rq.capture.package:
            parts.append(f"package {_escape(rq.capture.package)}")
        lines.append(f"<li>{_escape(rq.insurer)}: {', '.join(parts)}</li>")
    current_policy_line = ""
    if current_policy_source and current_policy_confirmed_at:
        # spec 006-policy-extraction-v2, FR-024: surface which generator and
        # which converter produced the confirmed reference, alongside the
        # source/confirmed-at fields v0.0.5 already surfaced here - only
        # when both are present, so a cache file written before this
        # feature existed (data-model.md's own additive-only invariant)
        # degrades to exactly v0.0.5's own footer shape.
        provenance_suffix = ""
        if current_policy_generator and current_policy_converter:
            provenance_suffix = (
                f", generator {_escape(current_policy_generator)}, "
                f"converter {_escape(current_policy_converter)}"
            )
        current_policy_line = (
            f"<p>Current-policy reference: {_escape(current_policy_source)}, "
            f"confirmed {_escape(current_policy_confirmed_at)}{provenance_suffix}.</p>"
        )
    return (
        "<footer><h2>Provenance</h2>"
        f"<ul>{''.join(lines)}</ul>"
        f"{current_policy_line}"
        "<p>Coverage limits and premiums are normalized per this feature's own arithmetic "
        "rules; every quote's premium figure shown above is a monthly-equivalent value "
        "(amount divided by term, rounded to 2 decimal places). The current policy's own "
        "premium row shows its raw figure with its own term, plus the same monthly-equivalent "
        "computation alongside it, so the two are comparable at a glance.</p>"
        "</footer>"
    )


def render_report(
    comparison: ComparisonResult,
    unmapped: list[str],
    failed: list[str],
    *,
    current_policy: CurrentPolicy | None = None,
    current_policy_source: str | None = None,
    current_policy_confirmed_at: str | None = None,
    current_policy_generator: str | None = None,
    current_policy_converter: str | None = None,
) -> str:
    """Render one self-contained HTML report (contracts section 5). Every
    argument is already fully resolved, in-memory data - this function
    performs no file I/O, no vault access, and constructs no browser.
    `current_policy` is accepted separately from `comparison` (which never
    embeds it) purely to render the current-policy column's own raw premium
    figure and per-line values (contracts section 5 item 3); passing `None`
    here when `comparison.has_current_policy` is `False` is always correct
    (there is nothing to render) and passing `None` when it is `True` still
    degrades gracefully (an empty current-policy column) rather than
    raising, since a caller error here should never take down report
    rendering.
    """
    body = (
        _render_header()
        + _render_banner(comparison)
        + _render_table(comparison, current_policy)
        + _render_unmapped(unmapped)
        + _render_failed(failed)
        + _render_footer(
            comparison,
            current_policy_source,
            current_policy_confirmed_at,
            current_policy_generator,
            current_policy_converter,
        )
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>Insurance Quote Comparison</title>\n"
        f"<style>{_STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_exclusion_report(asset_path: str = _TARGETED_ASSET) -> str:
    """The FR-064 report shape: when the targeted asset is excluded by the
    Director's own profile setting (the `"n/a"` sentinel), the report still
    renders, but states the exclusion plainly in place of a comparison
    table - never a bare refusal, never an empty comparison built from zero
    attempted data."""
    body = (
        "<h1>Insurance Quote Comparison</h1>"
        f"<div class=\"banner empty\">{_escape(asset_path)} excluded by profile (n/a) - "
        "no insurer journeys were run for this asset. Change currently_insured or policy_doc "
        "in your profile to a real value to include it.</div>"
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>Insurance Quote Comparison</title>\n"
        f"<style>{_STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def write_report(html: str, reports_dir: Path) -> Path:
    """Writes `reports_dir/quote-comparison-<date, YYYY-MM-DD, UTC>.html`,
    overwriting any existing report from the same UTC date - a report is a
    point-in-time snapshot, not an accumulating history the way captures
    are (data-model.md).

    Opens at mode `0600` before any content lands (NIT 6, Opus verifier,
    2026-08-26), mirroring `scripts/vault.py`'s and `headless/session.py`'s
    own `os.open(..., 0o600)` pattern - the rendered report is vault-grade
    local data (`CLAUDE.md`'s Secrets section), the same as `previews/`,
    and should never sit briefly world/group-readable before a
    write-then-chmod narrows it after the fact.
    """
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = reports_dir / f"quote-comparison-{date_str}.html"
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # missing file (first report of the day) or Windows.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows: no-op, mirrors scripts/vault.py's own FR-022 convention.
    return path
