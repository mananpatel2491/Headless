"""Policy PDF extraction, Director confirmation, and the `reports/policy/`
cache (spec 005-insurance-quote-comparison, User Story 3, research.md D15;
extended by spec 006-policy-extraction-v2).

`current_policy` is not hand-typed; it is derived, per insured asset, from
that asset's own `policy_doc` PDF: a layout-aware conversion
(`convert_document`), a candidate proposed by a local-only model
(`generate_candidate_via_local_model`, falling back automatically to the
v0.0.5 regex-based heuristics `_generate_regex_candidate`/`extract_candidate`
whenever the local model is unavailable, unreachable, or `--no-llm` was
passed), a mechanical sanity pass (`apply_sanity_pass`) that strips any
figure absent from the converted source text, and then Director confirmation
- unchanged from v0.0.5 - before anything can ever be compared against. No
model output ever reaches the cache or the comparison engine without passing
both gates (spec 006 FR-025, FR-026); no call of any kind ever reaches a
non-local endpoint (`headless/localllm.py`'s own localhost-only enforcement,
one layer up in `headless/config.py`).

`confirm_candidate` prints the extracted candidate to the Director's own
terminal before anything is cached - a deliberate, sole-purpose exception to
this codebase's usual value-free-output convention, the same documented
exception class `vault.py get` already established (spec FR-039, FR-053).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pypdf

from headless import localllm
from headless.capture import CurrentPolicy


@dataclass(frozen=True)
class ExtractionCandidate:
    """The raw, unconfirmed output of `extract_candidate` - shaped
    identically to `CurrentPolicy` plus `warnings` (value-free structural
    notes about what the heuristics could not confidently parse, never page
    text itself). Never itself a `CurrentPolicy`: the type distinction
    exists specifically so nothing can accidentally pass an unconfirmed
    candidate to `compare.build_comparison`, which only ever accepts
    `CurrentPolicy | None`."""

    insurer: str
    premium: dict
    coverages: list
    warnings: list

    def to_dict(self) -> dict:
        return {
            "insurer": self.insurer,
            "premium": dict(self.premium),
            "coverages": [dict(c) for c in self.coverages],
            "warnings": list(self.warnings),
        }


# Deterministic heuristics only (spec FR-051) - dollar amounts, split-limit
# patterns (e.g. "100,000/300,000"), a deductible-line pattern, and a
# premium/term pattern. None of this is fuzzy, learned, or LLM-derived; a
# pattern either matches or it does not, and a non-match becomes a
# `warnings` entry, never a guess.
_INSURER_RE = re.compile(
    r"([A-Z][A-Za-z&.,'/\- ]{2,60}?(?:Insurance|Mutual|Assurance|Casualty)\b[A-Za-z .]{0,20})"
)
_TERM_RE = re.compile(r"\b(6|12)\s*[- ]?month", re.IGNORECASE)
_PREMIUM_LINE_RE = re.compile(
    r"(?:Total Premium|Premium Due|Policy Premium)\D{0,10}\$?\s?([0-9][0-9,]*(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
_SPLIT_LIMIT_RE = re.compile(r"\$?\s?([0-9][0-9,]*)\s*/\s*\$?\s?([0-9][0-9,]*)")
_AMOUNT_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]{2})?)")
_DEDUCTIBLE_RE = re.compile(r"\$?\s?([0-9][0-9,]*)\s*deductible", re.IGNORECASE)

# Coverage-line slug -> the phrasings a declarations page might use for it.
# Deliberately not the same alias table headless/compare.py uses for
# normalizing a *captured quote's* own line names (research.md D10) - this
# one exists to locate a line inside PDF text, that one to match a captured
# quote's line against current_policy's. Both are hand-authored, not
# learned, for the same reason (D5).
_COVERAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bodily_injury": ("bodily injury liability", "bodily injury"),
    "property_damage": ("property damage liability", "property damage"),
    "collision": ("collision",),
    "comprehensive": ("comprehensive",),
    "uninsured_motorist": ("uninsured motorist", "underinsured motorist"),
    "medical_payments": ("medical payments", "personal injury protection", "pip"),
}

_WINDOW_CHARS = 200

# --- Term derivation (spec 006-policy-extraction-v2, FR-021, FR-022, D8) ---
# A deterministic helper, shared by both generators, that locates two dates
# near a policy-period label and computes a term as an average-day month
# span (the whole number of days between the two dates, divided by
# 30.436875 - the average Gregorian month length - and rounded to the
# nearest integer; FIX-FIRST 3, Opus verifier, 2026-08-29: this is not
# calendar-month subtraction, which would need to know each date's own
# day-of-month to decide whether a partial month rounds up or down) -
# closing the annual-policy gap ("Policy Period:" states two dates but
# never the phrase "12-month") that defeated v0.0.5's own _TERM_RE for
# every home-insurance declarations page research.md's own evidence names.
# Deliberately not fuzzy or learned: a date either parses in one of the
# recognized US formats or it does not, and the arithmetic is ordinary
# division and rounding, never an LLM call.
_PERIOD_LABEL_RE = re.compile(r"policy\s*period", re.IGNORECASE)
_DATE_TOKEN_RE = re.compile(
    # No trailing boundary: a scrambled, layout-lost extraction can butt a
    # date directly against the next label with no separating whitespace
    # (the real, verified artifact this helper exists to survive,
    # research.md: "12/01/2026To:12/01/2025From:Policy Period:"). The
    # leading negative lookbehind guards against matching a date fragment
    # embedded inside a longer digit run OR immediately after a "/" (NIT 7,
    # Opus verifier, 2026-08-29 - tightened from `(?<!\d)` alone; every
    # test in this suite, including the reversed-order butted-label case
    # above, still passes with this tighter lookbehind).
    #
    # Known, accepted false negative (documented, not silently wrong): a
    # real date glued directly to preceding, unrelated digits with no
    # separator at all (e.g. an invoice number immediately followed by a
    # date, "...99912/01/2026...") is indistinguishable from a date
    # fragment embedded inside that longer digit run, so this lookbehind
    # skips it - see
    # test_derive_term_from_dates_known_false_negative_when_a_date_is_glued_to_preceding_digits.
    r"(?<![\d/])(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4}|[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4})"
)
_DATE_FORMATS = ("%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%b. %d, %Y")
_DATE_WINDOW_CHARS = 150
_AVERAGE_DAYS_PER_MONTH = 30.436875


@dataclass(frozen=True)
class TermDerivation:
    """The outcome of `derive_term_from_dates` (data-model.md's own "Term
    derivation result" entity): a term string, plus a value-free warning
    when the computed span fell outside the two common terms (FR-021)."""

    term_months: str
    warning: str | None


def _parse_date_token(token: str) -> datetime | None:
    cleaned = token.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _find_period_dates(text: str) -> tuple[datetime, datetime] | None:
    label_match = _PERIOD_LABEL_RE.search(text)
    if label_match is None:
        return None
    start = max(0, label_match.start() - _DATE_WINDOW_CHARS)
    end = min(len(text), label_match.end() + _DATE_WINDOW_CHARS)
    window = text[start:end]
    found: list[datetime] = []
    for match in _DATE_TOKEN_RE.finditer(window):
        parsed = _parse_date_token(match.group(1))
        if parsed is not None:
            found.append(parsed)
        if len(found) == 2:
            break
    if len(found) < 2:
        return None
    return found[0], found[1]


def _month_span(date_a: datetime, date_b: datetime) -> int:
    delta_days = abs((date_b - date_a).days)
    return round(delta_days / _AVERAGE_DAYS_PER_MONTH)


def derive_term_from_dates(text: str) -> TermDerivation | None:
    """FR-021: locate two dates, in common United States date formats, near
    a policy-period label in `text`, and compute a term as the average-day
    month span between them (`_month_span`: whole days apart, divided by
    the average Gregorian month length of 30.436875, rounded to the
    nearest integer - not calendar-month subtraction) - regardless of
    which one reads first (the real document's own reversed "To:" date
    preceding its "From:" date is exactly the case this helper exists to
    survive, research.md). A span of eleven to thirteen months yields
    `"12"`; five to seven months yields `"6"`; any other span yields the
    exact rounded month count, with a value-free warning naming only the
    computed count. Returns `None` when fewer than two dates are found
    near the label - the caller then leaves `term_months` exactly as its
    own generator proposed (FR-022)."""
    dates = _find_period_dates(text)
    if dates is None:
        return None
    span = _month_span(dates[0], dates[1])
    if 11 <= span <= 13:
        return TermDerivation(term_months="12", warning=None)
    if 5 <= span <= 7:
        return TermDerivation(term_months="6", warning=None)
    return TermDerivation(
        term_months=str(span),
        warning=f"term derived as {span} months, outside the two common terms",
    )


def _extract_text(pdf_path: Path, reader_factory: Callable[[str], object]) -> str | None:
    try:
        reader = reader_factory(str(pdf_path))
        pages = getattr(reader, "pages", [])
        text = "\n".join((page.extract_text() or "") for page in pages)
    except Exception:
        return None
    return text or None


def _generate_regex_candidate(text: str) -> ExtractionCandidate | None:
    """The regex-based generator (v0.0.5's own deterministic heuristics,
    spec 006's automatic-fallback generator, FR-004), operating on
    already-extracted text - shared by `extract_candidate`'s own public
    contract (pypdf's raw-text path, unchanged) and the v2 dispatch
    (`extract_candidate_v2`), which may hand it layout-aware Markdown text
    instead. FR-022: also tries the shared date-arithmetic helper
    (`derive_term_from_dates`) whenever its own "N-month" phrase pattern
    does not match, closing the annual-policy gap in this generator too,
    not only the local-model one (research.md D8)."""
    warnings: list[str] = []

    insurer_match = _INSURER_RE.search(text)
    insurer = insurer_match.group(1).strip() if insurer_match else ""
    if not insurer:
        warnings.append("no insurer detected")

    term_match = _TERM_RE.search(text)
    term_derivation: TermDerivation | None = None
    if term_match:
        term_months = term_match.group(1)
    else:
        term_derivation = derive_term_from_dates(text)
        term_months = term_derivation.term_months if term_derivation else ""
    if not term_months:
        warnings.append("no term detected")
    elif term_derivation is not None and term_derivation.warning:
        warnings.append(term_derivation.warning)

    premium_match = _PREMIUM_LINE_RE.search(text)
    amount = premium_match.group(1).replace(",", "") if premium_match else ""
    if not amount:
        warnings.append("no premium detected")

    coverages: list[dict] = []
    lower_text = text.lower()
    for line_slug, keywords in _COVERAGE_KEYWORDS.items():
        found_at = None
        for keyword in keywords:
            idx = lower_text.find(keyword)
            if idx != -1:
                found_at = idx
                break
        if found_at is None:
            continue
        window = text[found_at:found_at + _WINDOW_CHARS]
        split_match = _SPLIT_LIMIT_RE.search(window)
        if split_match:
            limit = f"{split_match.group(1)}/{split_match.group(2)}"
        else:
            amount_match = _AMOUNT_RE.search(window)
            limit = amount_match.group(1) if amount_match else ""
        if not limit:
            warnings.append(f"no limit detected for {line_slug}")
            continue
        deductible_match = _DEDUCTIBLE_RE.search(window)
        deductible = deductible_match.group(1) if deductible_match else ""
        coverages.append(
            {"line": line_slug, "limit": limit, "deductible": deductible, "premium": ""}
        )

    if not coverages:
        return None

    return ExtractionCandidate(
        insurer=insurer,
        premium={"term_months": term_months, "amount": amount},
        coverages=coverages,
        warnings=warnings,
    )


def extract_candidate(
    pdf_path: Path, *, reader_factory: Callable[[str], object] | None = None
) -> ExtractionCandidate | None:
    """Extract a best-effort `CurrentPolicy`-shaped candidate from a PDF's
    own text (spec FR-051, FR-052, research.md D15). `reader_factory`
    defaults to `pypdf.PdfReader`; tests inject a fake double with a
    `.pages` list of objects exposing `extract_text()`, so no real binary
    PDF asset is ever needed to exercise this function.

    Returns `None` (not an exception) when the PDF cannot be read at all,
    or when zero coverage lines were parsed - both are the same "nothing to
    offer the Director" outcome (data-model.md); a scanned-image PDF with
    no text layer degrades the same way, never via OCR (out of scope).
    """
    factory = reader_factory or pypdf.PdfReader
    text = _extract_text(Path(pdf_path), factory)
    if not text:
        return None
    return _generate_regex_candidate(text)


# --- Layout-aware conversion (spec 006-policy-extraction-v2, FR-001, FR-002, D2) ---

_LAYOUT_CONVERTER_NAME = "pymupdf4llm"
_FALLBACK_CONVERTER_NAME = "pypdf-raw"


@dataclass(frozen=True)
class ConvertedDocument:
    """The in-memory result of the conversion step (data-model.md). Never
    written to disk; never printed on its own - only a candidate built from
    it is ever shown to the Director."""

    text: str
    converter: str


def _default_layout_converter(pdf_path: str) -> str:
    """Production wiring: `pymupdf4llm.to_markdown`. A local import so an
    import failure (the package missing) is FR-002's own "cannot be
    imported" fallback trigger, not a module-load-time failure of this
    whole file. Every test injects a fake `layout_converter` instead
    (NFR-001) - this function is never invoked by the default `pytest -q`
    suite."""
    import pymupdf4llm

    return pymupdf4llm.to_markdown(pdf_path)


def convert_document(
    pdf_path: Path,
    *,
    reader_factory: Callable[[str], object] | None = None,
    layout_converter: Callable[[str], str] | None = None,
) -> ConvertedDocument | None:
    """FR-001, FR-002: convert `pdf_path`'s content to layout-aware Markdown
    first (`layout_converter`, defaulting to a real `pymupdf4llm.to_markdown`
    call); on an import failure or any exception the converter call raises,
    fall back to the existing `pypdf` raw-text extraction (v0.0.5's own
    path, `_extract_text`). Returns `None` (FR-015) when neither path
    yields any text - the same "nothing to offer the Director" outcome
    v0.0.5 already defines for an unreadable PDF."""
    converter = layout_converter or _default_layout_converter
    try:
        text = converter(str(pdf_path))
    except Exception:
        text = None
    if text:
        return ConvertedDocument(text=text, converter=_LAYOUT_CONVERTER_NAME)

    factory = reader_factory or pypdf.PdfReader
    fallback_text = _extract_text(Path(pdf_path), factory)
    if not fallback_text:
        return None
    return ConvertedDocument(text=fallback_text, converter=_FALLBACK_CONVERTER_NAME)


# --- Local-model candidate generation (spec 006-policy-extraction-v2, FR-004, FR-005) ---

_LOCAL_MODEL_PROMPT_TEMPLATE = (
    "You are extracting structured data from an insurance policy declarations "
    "page that has been converted to text below. Read the whole document and "
    "propose a JSON object with exactly these keys: \"insurer\" (string), "
    "\"premium\" (an object with \"term_months\" and \"amount\", both strings), "
    "and \"coverages\" (an array of objects, each with \"line\", \"limit\", "
    "\"deductible\", and \"premium\", all strings). Every figure you propose "
    "MUST be copied verbatim from the document text below - never invented, "
    "estimated, or inferred from outside knowledge. If a figure is not "
    "present in the document, use an empty string for it. Respond with ONLY "
    "the JSON object, no other text.\n\nDocument:\n{text}"
)


def _build_extraction_prompt(text: str) -> str:
    return _LOCAL_MODEL_PROMPT_TEMPLATE.format(text=text)


def generate_candidate_via_local_model(
    document: ConvertedDocument,
    *,
    model: str,
    url: str,
    transport: Callable[[str, dict, float], dict] | None = None,
    timeout: float = localllm.DEFAULT_TIMEOUT,
) -> ExtractionCandidate | None:
    """FR-004, FR-005, FR-010: builds the extraction prompt from
    `document.text`, calls `headless/localllm.py`'s transport, and
    constructs an `ExtractionCandidate` from a successful, schema-valid
    response. FR-020/FR-022: the shared date-arithmetic helper
    (`derive_term_from_dates`) always supplies or overrides `term_months`
    when two policy-period dates are found in `document.text` - a value-free
    note records an override only when the model's own claim disagreed with
    a real derived value (never merely omitted).

    Returns `None` (never raises) on any failure classification from
    contracts/extraction-v2.md section 1 - the caller falls back to the
    regex-based generator and records the one value-free warning (FR-013)."""
    prompt = _build_extraction_prompt(document.text)
    try:
        raw = localllm.generate_candidate(
            model=model, url=url, prompt=prompt, transport=transport, timeout=timeout
        )
    except localllm.LocalModelUnavailable:
        return None

    warnings: list[str] = []
    raw_premium = raw.get("premium") if isinstance(raw.get("premium"), dict) else {}
    claimed_term = raw_premium.get("term_months", "") or ""

    term_derivation = derive_term_from_dates(document.text)
    if term_derivation is not None:
        if claimed_term and claimed_term != term_derivation.term_months:
            warnings.append(
                "term_months derived from policy-period dates overrode the model's own claim"
            )
        term_months = term_derivation.term_months
        if term_derivation.warning:
            warnings.append(term_derivation.warning)
    else:
        term_months = claimed_term

    coverages = [
        {
            "line": c.get("line", ""),
            "limit": c.get("limit", ""),
            "deductible": c.get("deductible", ""),
            "premium": c.get("premium", ""),
        }
        for c in raw.get("coverages", [])
        if isinstance(c, dict)
    ]

    return ExtractionCandidate(
        insurer=raw.get("insurer", "") or "",
        premium={"term_months": term_months, "amount": raw_premium.get("amount", "") or ""},
        coverages=coverages,
        warnings=warnings,
    )


# --- The mechanical sanity pass (spec 006-policy-extraction-v2, FR-017 through FR-020, D5) ---


_DIGIT_RUN_RE = re.compile(r"\d[\d.]*")


def _strip_currency_formatting(value: str) -> str:
    """Removes `$`, commas, and whitespace only - a decimal point survives,
    since it is significant to the token comparison below (`"753.25"` is a
    different token from `"75325"`)."""
    return re.sub(r"[\s,$]", "", value or "")


def _normalize_token(value: str) -> str:
    """Strips a trailing `.00`/`.0`-style all-zero fractional part so
    `"15000.00"` and `"15000"` compare equal (contracts section 2's own
    tolerance) - applied identically to a source-derived token and a
    proposed figure before comparing them, so a real decimal amount
    (`"753.25"`) is unaffected."""
    if "." in value:
        integer_part, _, fractional_part = value.partition(".")
        if fractional_part and set(fractional_part) == {"0"}:
            return integer_part or "0"
    return value


def _source_digit_tokens(source_text: str) -> set[str]:
    """FIX-FIRST 2 (Opus verifier, 2026-08-29): tokenizes the source into
    its own maximal digit-run tokens (each normalized per
    `_normalize_token`), once per sanity-pass call. A proposed figure is
    checked for exact membership in this set - never substring containment
    against one long concatenated digit blob, which an adversarial review
    proved accepts a hallucinated figure sharing a digit-run suffix with an
    unrelated real one (`"50,000"` against a source that only ever states
    `"150,000"`; `"$3,000"` against `"$300,000"`; any figure that happens to
    be a trailing substring of a larger real number). Currency symbols and
    commas are stripped before tokenizing so `"$150,000"` tokenizes to the
    single token `"150000"`; a decimal point survives so `"$753.25"`
    tokenizes to `"753.25"`, distinct from `"75325"`. `"/"` (a split-limit
    separator) is not a digit-run character, so `"100,000/300,000"` already
    tokenizes into two independent tokens, `"100000"` and `"300000"`."""
    stripped = re.sub(r"[,$]", "", source_text or "")
    return {_normalize_token(token) for token in _DIGIT_RUN_RE.findall(stripped)}


def _figure_present(value: str, source_tokens: set[str]) -> bool:
    """FIX-FIRST 2: a proposed figure passes only when its own normalized
    form exactly equals one token in `source_tokens` (with the `.00`/`.0`
    tolerance `_normalize_token` applies to both sides) - never mere
    substring containment. A split value (`"100,000/300,000"`) is checked
    as two independent tokens, both required (contracts section 2). An
    empty `value` has nothing to check - trivially present. NIT 10 (Opus
    verifier, 2026-08-29): a part containing no digit at all (`"N/A"`,
    `"n/a"`) is not a figure - it passes through untouched, since there is
    nothing for a digit-run check to verify; this only applies per
    `"/"`-split part, so a genuinely all-text value never trips the
    "figure absent" warning."""
    if not value:
        return True
    for part in value.split("/"):
        cleaned = _strip_currency_formatting(part)
        if not cleaned:
            return False
        if not any(ch.isdigit() for ch in cleaned):
            continue  # NIT 10: non-numeric text is not a figure
        if _normalize_token(cleaned) not in source_tokens:
            return False
    return True


def apply_sanity_pass(candidate: ExtractionCandidate, source_text: str) -> ExtractionCandidate:
    """FR-017 through FR-020, FR-026: strips any figure absent from
    `source_text` after normalization, replacing it with a value-free
    warning naming only the field (never the value, never a source
    fragment). Runs against every candidate, from either generator, before
    it ever reaches `confirm_candidate` - a regex-derived figure is by
    construction a substring of its own source, so this trivially passes
    for it (D5's own "costs nothing to apply uniformly" rationale).

    `insurer` and each coverage line's own `line` name are text, not
    figures, and are exempt (FR-028). `term_months` is exempt only when it
    equals what `derive_term_from_dates` itself currently derives from
    `source_text` (FR-019) - recomputing the derivation here, rather than
    threading a boolean through every caller, is how this function
    determines "was this term derived by the date-arithmetic helper"
    without `ExtractionCandidate`'s own unchanged shape (FR-025) needing a
    new field to carry that provenance."""
    source_tokens = _source_digit_tokens(source_text)
    warnings = list(candidate.warnings)

    premium = dict(candidate.premium)
    amount = premium.get("amount", "")
    if amount and not _figure_present(amount, source_tokens):
        premium["amount"] = ""
        warnings.append("a proposed premium amount did not appear in the document and was removed")

    term_months = premium.get("term_months", "")
    term_derivation = derive_term_from_dates(source_text)
    term_exempt = term_derivation is not None and term_months == term_derivation.term_months
    if term_months and not term_exempt and not _figure_present(term_months, source_tokens):
        premium["term_months"] = ""
        warnings.append("a proposed term_months did not appear in the document and was removed")

    coverages = []
    for coverage in candidate.coverages:
        entry = dict(coverage)
        line_name = entry.get("line", "") or "coverage"
        for field_name in ("limit", "deductible", "premium"):
            value = entry.get(field_name, "")
            if value and not _figure_present(value, source_tokens):
                entry[field_name] = ""
                warnings.append(
                    f"a proposed {line_name} {field_name} did not appear in the document and was removed"
                )
        coverages.append(entry)

    return ExtractionCandidate(
        insurer=candidate.insurer,
        premium=premium,
        coverages=coverages,
        warnings=warnings,
    )


# --- The v2 pipeline dispatch (spec 006-policy-extraction-v2, D1, D6) ---

_LOCAL_MODEL_FALLBACK_NOTE = "local model unavailable, fell back to the regex-based generator"


def _local_candidate_is_usable(candidate: ExtractionCandidate) -> bool:
    """FIX-FIRST 1 (Opus verifier, 2026-08-29): a schema-valid local-model
    response that carries no coverages at all, or whose every figure field
    (`premium.amount` plus every coverage line's own `limit`/`deductible`/
    `premium`) is empty, is not a usable candidate - confirming it would
    hand the Director an empty policy with zero warnings, silently worse
    than what v0.0.5's own regex generator would have produced from the
    same document. FR-004's own wording ("used whenever the local-model
    attempt does not produce a usable candidate") already anticipated this
    case; this function is what makes the dispatch below actually honor
    it, treating a schema-valid-but-unusable response exactly like any
    other failed attempt (one value-free note, automatic regex fallback -
    contracts/extraction-v2.md section 1's own classification table)."""
    if not candidate.coverages:
        return False
    figures = [candidate.premium.get("amount", "")]
    for coverage in candidate.coverages:
        figures.append(coverage.get("limit", ""))
        figures.append(coverage.get("deductible", ""))
        figures.append(coverage.get("premium", ""))
    return any(figures)


def extract_candidate_v2(
    pdf_path: Path,
    *,
    config,
    use_llm: bool = True,
    reader_factory: Callable[[str], object] | None = None,
    layout_converter: Callable[[str], str] | None = None,
    transport: Callable[[str, dict, float], dict] | None = None,
) -> tuple[ExtractionCandidate, str, str] | None:
    """The full spec 006 pipeline: convert (`convert_document`) -> generate
    (the local model first, unless `use_llm` is `False`; the regex-based
    generator automatically whenever the local-model attempt does not
    produce a usable candidate, FR-004, `_local_candidate_is_usable`) -> the
    mechanical sanity pass (`apply_sanity_pass`). The Director's own
    confirmation gate (`confirm_candidate`) is unchanged and runs after
    this function returns (FR-026) - this function never calls it itself.

    Returns `(candidate, generator_name, converter_name)`, or `None` when
    the converted document carries no extractable text (FR-015) or the
    regex-based generator itself parses zero coverage lines (unchanged from
    v0.0.5). `generator_name` is `"regex-v1"` or `"local-llm:<model>"`;
    `converter_name` is the layout-aware converter's own name or
    `"pypdf-raw"` (FR-023). NIT 8 (Opus verifier, 2026-08-29): when the
    local-model attempt already failed (or was schema-valid but unusable)
    AND the regex-based fallback also finds zero coverage lines, this
    function still returns `None` (unchanged outcome, contracts section 3
    row 5) but prints the one value-free fallback note directly - the only
    way to keep a down/unusable local model distinguishable from a
    genuinely unreadable PDF (contracts section 3 row 2) when there is no
    longer any `ExtractionCandidate` object left to carry that note as a
    `warnings` entry."""
    document = convert_document(pdf_path, reader_factory=reader_factory, layout_converter=layout_converter)
    if document is None or not document.text:
        return None

    candidate: ExtractionCandidate | None = None
    generator_name = "regex-v1"
    llm_failed = False

    if use_llm:
        candidate = generate_candidate_via_local_model(
            document, model=config.ollama_model, url=config.ollama_url, transport=transport
        )
        if candidate is not None and _local_candidate_is_usable(candidate):
            generator_name = f"local-llm:{config.ollama_model}"
        else:
            candidate = None
            llm_failed = True

    if candidate is None:
        regex_candidate = _generate_regex_candidate(document.text)
        if regex_candidate is None:
            if llm_failed:
                print(f"note: {_LOCAL_MODEL_FALLBACK_NOTE}")
            return None
        if llm_failed:
            regex_candidate = ExtractionCandidate(
                insurer=regex_candidate.insurer,
                premium=dict(regex_candidate.premium),
                coverages=[dict(c) for c in regex_candidate.coverages],
                warnings=[*regex_candidate.warnings, _LOCAL_MODEL_FALLBACK_NOTE],
            )
        candidate = regex_candidate
        generator_name = "regex-v1"

    candidate = apply_sanity_pass(candidate, document.text)
    return candidate, generator_name, document.converter


def confirm_candidate(
    candidate: ExtractionCandidate, *, input_fn: Callable[[str], str] = input
) -> CurrentPolicy | None:
    """Prints `candidate` (the deliberate, sole print-a-value exception this
    mechanism shares with `vault.py get`, spec FR-053) and prompts, via the
    injectable `input_fn` (never a real terminal in a test): accept as
    printed, or paste a corrected JSON document at a follow-up plain-text
    prompt (not hidden - the candidate was already shown in the clear
    moments before). Returns the confirmed `CurrentPolicy` on either accept
    or a valid correction; returns `None` on decline or an uncorrectable
    input - in every `None` case, no cache write follows (spec FR-054,
    FR-055)."""
    print("Extracted current-policy candidate (your own data, printed for your review):")
    print(json.dumps(candidate.to_dict(), indent=2))
    choice = input_fn("Accept as printed, correct it, or decline? [a/c/d]: ").strip().lower()
    if choice in ("a", "accept"):
        return CurrentPolicy(
            insurer=candidate.insurer,
            premium=dict(candidate.premium),
            coverages=[dict(c) for c in candidate.coverages],
        )
    if choice in ("c", "correct"):
        raw = input_fn("Paste the corrected JSON document (insurer/premium/coverages): ")
        try:
            data = json.loads(raw)
            return CurrentPolicy.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            print("REFUSED: corrected document could not be parsed; nothing cached")
            return None
    return None  # decline, or anything not recognized as accept/correct


@dataclass(frozen=True)
class PolicyReference:
    """A confirmed `CurrentPolicy` plus its own provenance and the asset key
    it is cached under (data-model.md). `generator`/`converter` are additive
    fields spec 006-policy-extraction-v2 introduces (FR-023): which code
    path produced the confirmed candidate (`"regex-v1"` or
    `"local-llm:<model-name>"`) and which produced the source text it was
    built from (the layout-aware converter's own name, or `"pypdf-raw"`).
    Their defaults exist for construction convenience only (a v0.0.5-style
    caller that never learns about this feature); `scripts/policy_extract.py`
    always supplies the pipeline's own real values explicitly."""

    policy: CurrentPolicy
    asset_key: str
    source_path: str
    confirmed_at: str
    generator: str = "regex-v1"
    converter: str = "pypdf-raw"

    def to_dict(self) -> dict:
        data = self.policy.to_dict()
        data["source_path"] = self.source_path
        data["confirmed_at"] = self.confirmed_at
        data["generator"] = self.generator
        data["converter"] = self.converter
        return data


def derive_asset_key(array_name: str, type_value: str) -> str:
    """`<array-name>.<type>`, dots replaced with hyphens:
    `vehicles.primary` becomes `vehicles-primary` (FR-056)."""
    return f"{array_name}-{type_value}"


def write_policy_reference(reference: PolicyReference, reports_dir: Path) -> Path:
    """Writes `reports_dir/policy/<asset-key>.json`, mode `0600` where the
    platform supports it (a documented no-op on Windows). Whole-file
    replace on every write - a policy reference has exactly one current
    value per asset.

    Opens at mode `0600` before any content lands (NIT 6, Opus verifier,
    2026-08-26), mirroring `scripts/vault.py`'s and `headless/session.py`'s
    own `os.open(..., 0o600)` pattern - not `write_text` then `chmod`
    after, which leaves the Director's own confirmed premium and coverage
    data briefly world/group-readable at the process's default umask
    before the narrower mode lands. A pre-write `chmod` (best-effort)
    narrows an already-existing file - one from an earlier, looser-mode
    write - before it is reopened for truncation, since `os.open`'s own
    `mode` argument only takes effect when a file is newly created.
    """
    policy_dir = Path(reports_dir) / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    path = policy_dir / f"{reference.asset_key}.json"
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # missing file (first write) or Windows: both expected, both harmless here.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(reference.to_dict(), indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows: no-op, mirrors scripts/vault.py's own FR-022 convention.
    return path


def read_policy_reference(asset_key: str, reports_dir: Path) -> CurrentPolicy | None:
    """Reads and parses the one file for `asset_key`; `None` when it does
    not exist or fails to parse (spec FR-058) - a malformed cache is
    treated exactly like a missing one, never a hard refusal."""
    path = Path(reports_dir) / "policy" / f"{asset_key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CurrentPolicy.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def read_policy_reference_provenance(asset_key: str, reports_dir: Path) -> tuple[str, str, str, str] | None:
    """Reads the same cache file `read_policy_reference` reads, but returns
    only its own provenance (`source_path`, `confirmed_at`, `generator`,
    `converter`) rather than the embedded `CurrentPolicy`. Exists so the
    report's provenance footer can satisfy FR-059/FR-024 (naming the
    confirmed reference's own source, confirmation date, generator, and
    converter) without `render_report` itself touching the filesystem, and
    without changing `read_policy_reference`'s own contracted
    `CurrentPolicy | None` return shape. `None` under the exact same
    conditions `read_policy_reference` returns `None` (missing or
    unparseable file). `generator`/`converter` default to `"unknown"` when
    absent - true for every cache file written before spec
    006-policy-extraction-v2 existed (data-model.md's own additive-only
    invariant); never treated as an error."""
    path = Path(reports_dir) / "policy" / f"{asset_key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (
            data["source_path"],
            data["confirmed_at"],
            data.get("generator", "unknown"),
            data.get("converter", "unknown"),
        )
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def is_excluded(asset: dict) -> bool:
    """`True` when `asset.get("currently_insured") == "n/a"` or
    `asset.get("policy_doc") == "n/a"` (spec FR-061). One function, two
    callers (`scripts/policy_extract.py`, `scripts/quote_compare.py`), so
    the sentinel's own meaning is defined in exactly one place. Never
    mutates its input."""
    return asset.get("currently_insured") == "n/a" or asset.get("policy_doc") == "n/a"
