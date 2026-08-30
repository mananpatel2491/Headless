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
from dataclasses import dataclass, field
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
    `CurrentPolicy | None`.

    spec 007-extraction-fidelity, FR-022/FR-023 (D5): ten additive fields
    beyond spec 006's own `insurer`/`premium`/`coverages`/`warnings` -
    everything else a real declarations page routinely states, groundwork
    for a future comparison feature. Every field defaults to its own empty
    shape so a caller built against spec 006's own three-field contract
    (test doubles included) keeps constructing this type unchanged.
    `headless/compare.py`'s own comparison engine ignores every one of
    these fields (FR-028) except through the alias-table extension."""

    insurer: str
    premium: dict
    coverages: list
    warnings: list
    policy_number: str = ""
    effective_date: str = ""
    expiration_date: str = ""
    policy_level_deductibles: list = field(default_factory=list)
    asset: dict = field(default_factory=dict)
    named_insureds: list = field(default_factory=list)
    excluded_drivers: list = field(default_factory=list)
    discounts: list = field(default_factory=list)
    fees: list = field(default_factory=list)
    subtotal: str = ""

    def to_dict(self) -> dict:
        return {
            "insurer": self.insurer,
            "premium": dict(self.premium),
            "coverages": [dict(c) for c in self.coverages],
            "warnings": list(self.warnings),
            "policy_number": self.policy_number,
            "effective_date": self.effective_date,
            "expiration_date": self.expiration_date,
            "policy_level_deductibles": [dict(d) for d in self.policy_level_deductibles],
            "asset": dict(self.asset),
            "named_insureds": list(self.named_insureds),
            "excluded_drivers": list(self.excluded_drivers),
            "discounts": [dict(d) for d in self.discounts],
            "fees": [dict(f) for f in self.fees],
            "subtotal": self.subtotal,
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

# --- Term derivation (spec 006-policy-extraction-v2 FR-021/FR-022, amended
# by spec 007-extraction-fidelity FR-006 through FR-011, D2) ---
# A deterministic helper, shared by both generators, that locates every
# occurrence of a policy-period label and computes a term as an average-day
# month span (the whole number of days between the earliest and latest date
# collected, divided by 30.436875 - the average Gregorian month length -
# and rounded to the nearest integer; FIX-FIRST 3, Opus verifier,
# 2026-08-29: this is not calendar-month subtraction, which would need to
# know each date's own day-of-month to decide whether a partial month
# rounds up or down) - closing the annual-policy gap ("Policy Period:"
# states two dates but never the phrase "12-month") that defeated v0.0.5's
# own _TERM_RE for every home-insurance declarations page research.md's own
# evidence names. Deliberately not fuzzy or learned: a date either parses
# in one of the recognized US formats or it does not, and the arithmetic is
# ordinary division and rounding, never an LLM call.
#
# spec 007-extraction-fidelity, D2 (FR-006 through FR-009): an independent
# audit against three real declarations PDFs proved the original
# before-and-after window, first-two-dates-found rule mis-paired an
# unrelated date (a statement date, an issue date) positioned before the
# label with the real period's own start date on two of three documents,
# deriving a nonsense term and silently overriding a correct model claim
# (spec 006's own FR-020). The corrected rule scans EVERY label occurrence,
# windows ONLY the text that follows each occurrence (never before), and
# computes the span from the MAXIMUM and MINIMUM date collected across
# every window - never merely the first two dates encountered. Known,
# accepted trade-off (D2's own "Alternatives considered"): a document whose
# real period dates sit entirely BEFORE the label, with nothing after it at
# all, is no longer derivable by this helper at all (see
# test_derive_term_from_dates_known_residual_when_both_dates_precede_the_label
# below) - widening the window back to include "before" text would
# reopen exactly the class of error this fix exists to close.
_PERIOD_LABEL_RE = re.compile(r"policy\s*period", re.IGNORECASE)
# spec 007-extraction-fidelity, IMPORTANT 4 (Opus verifier, 2026-08-30): a
# real declarations page routinely carries a "Prior Policy Period" (or
# "Previous"/"Former"/"Expiring") section alongside the current one - two
# adjacent periods, each with its own two dates. Scanning every label
# occurrence (FR-006) without excluding this shape let the corrected
# max-minus-min rule (FR-008) span a prior period's own start date to the
# current period's own end date, deriving a false combined term with no
# warning - a regression against spec 006's own regex-path behavior, which
# never encountered this shape (it only ever inspected the first label
# occurrence). A period-label occurrence immediately preceded (within
# `_LABEL_EXCLUSION_LOOKBACK_CHARS`) by one of these words is excluded: its
# own window is never scanned as a "surviving" occurrence, AND every date
# match found inside its own window is excluded from every OTHER
# occurrence's own collection too (`_find_period_dates`'s own
# `excluded_positions` set) - a prior-period date must never enter the
# collected set at all, regardless of whether some other, non-excluded
# occurrence's own broad forward window happens to sweep over the same
# text incidentally.
_EXCLUDED_LABEL_PRECEDER_RE = re.compile(r"\b(prior|previous|former|expiring)\b", re.IGNORECASE)
_LABEL_EXCLUSION_LOOKBACK_CHARS = 20
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
# spec 007-extraction-fidelity FR-007: after-only, ~400 characters - was
# 150 characters before AND after under spec 006's own original rule.
_DATE_WINDOW_CHARS = 400
_AVERAGE_DAYS_PER_MONTH = 30.436875


@dataclass(frozen=True)
class TermDerivation:
    """The outcome of `derive_term_from_dates` (data-model.md's own "Term
    derivation result" entity): a term string, plus a value-free warning
    when the computed span fell outside the two common terms (FR-021)."""

    term_months: str
    warning: str | None


@dataclass(frozen=True)
class _TermResolution:
    """Internal only (spec 007-extraction-fidelity, D2's own restated
    precedence order): the outcome of `_resolve_authoritative_term` -
    `source` names which rule supplied `term_months`, purely so a caller
    can phrase an "overrode the model's own claim" warning correctly
    without re-deriving which rule fired."""

    term_months: str
    warning: str | None
    source: str  # "phrase" or "date"


def _parse_date_token(token: str) -> datetime | None:
    cleaned = token.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _is_excluded_label_occurrence(text: str, label_match: "re.Match[str]") -> bool:
    lookback_start = max(0, label_match.start() - _LABEL_EXCLUSION_LOOKBACK_CHARS)
    preceding = text[lookback_start:label_match.start()]
    return _EXCLUDED_LABEL_PRECEDER_RE.search(preceding) is not None


def _find_period_dates(text: str) -> tuple[datetime, datetime, int] | None:
    """FR-006 through FR-009: scans every `_PERIOD_LABEL_RE` occurrence in
    `text` (not only the first), windows only the text that follows each
    occurrence's own end (never before it - FR-007), and collects every
    date that parses across every such window into a `set` (so a date
    repeated across two windows, e.g. the label appearing once in a
    summary section and again in a detailed schedule, counts once).

    IMPORTANT 4 (Opus verifier, 2026-08-30): an occurrence immediately
    preceded by "prior"/"previous"/"former"/"expiring"
    (`_is_excluded_label_occurrence`) is excluded from contributing its own
    window as a "surviving" occurrence, AND every date match found inside
    its own window is recorded in `excluded_positions` (by absolute text
    offset) so no OTHER occurrence's own window can pick up that same
    prior-period date incidentally. Every occurrence's own window (excluded
    or not) is additionally capped at the START of the NEXT label
    occurrence, whichever comes first against the ~400-character bound -
    without this cap, an excluded occurrence positioned BEFORE a surviving
    one would sweep its own overly broad forward window across the
    surviving occurrence's own text too, wrongly marking the surviving
    period's own real dates as "excluded" purely because they were also
    reachable (a bug this exact ordering exposed during verification: only
    capping the window fixes both reading orders symmetrically).

    Returns `(earliest, latest, distinct_count)` for at least two DISTINCT
    surviving dates collected this way, or `None` when fewer than two
    distinct dates survive - the caller then leaves `term_months` exactly
    as its own generator proposed. `distinct_count` lets the caller warn
    when more than two distinct dates were collected (IMPORTANT 4(ii))."""
    occurrences = list(_PERIOD_LABEL_RE.finditer(text))

    def _window_bounds(index: int) -> tuple[int, int]:
        start = occurrences[index].end()
        end = min(len(text), start + _DATE_WINDOW_CHARS)
        if index + 1 < len(occurrences):
            end = min(end, occurrences[index + 1].start())
        return start, end

    excluded_positions: set[int] = set()
    for index, label_match in enumerate(occurrences):
        if not _is_excluded_label_occurrence(text, label_match):
            continue
        start, end = _window_bounds(index)
        for match in _DATE_TOKEN_RE.finditer(text[start:end]):
            excluded_positions.add(start + match.start())

    found: set[datetime] = set()
    for index, label_match in enumerate(occurrences):
        if _is_excluded_label_occurrence(text, label_match):
            continue
        start, end = _window_bounds(index)
        for match in _DATE_TOKEN_RE.finditer(text[start:end]):
            if (start + match.start()) in excluded_positions:
                continue
            parsed = _parse_date_token(match.group(1))
            if parsed is not None:
                found.add(parsed)
    if len(found) < 2:
        return None
    return min(found), max(found), len(found)


def _month_span(date_a: datetime, date_b: datetime) -> int:
    delta_days = abs((date_b - date_a).days)
    return round(delta_days / _AVERAGE_DAYS_PER_MONTH)


def _term_from_span(span: int) -> TermDerivation:
    """The span-to-term mapping shared by every date-based term
    computation in this module (spec 006's own unchanged arithmetic,
    contracts/fidelity.md section 2's own table row: "unchanged - only
    which dates feed this mapping changes") - `derive_term_from_dates`
    (below) and the schema extension's own `effective_date`/
    `expiration_date` computation (FR-024, `apply_sanity_pass`) both
    reduce to this one function so the two never drift into two different
    rounding rules."""
    if 11 <= span <= 13:
        return TermDerivation(term_months="12", warning=None)
    if 5 <= span <= 7:
        return TermDerivation(term_months="6", warning=None)
    return TermDerivation(
        term_months=str(span),
        warning=f"term derived as {span} months, outside the two common terms",
    )


# IMPORTANT 4 (Opus verifier, 2026-08-30): a value-free note - names only
# the fact that more than two distinct dates survived, never any date
# value - so the Director can see that a multi-period document was in
# play even when the prior-period exclusion above worked correctly.
_MULTIPLE_DATES_WARNING = (
    "more than two distinct dates were found across the surviving "
    "policy-period windows; the earliest and latest were used"
)


def derive_term_from_dates(text: str) -> TermDerivation | None:
    """FR-006 through FR-009: locate every occurrence of a policy-period
    label in `text`, collect every date that parses (in common United
    States date formats) across the text that follows each occurrence
    only, and compute a term as the average-day month span (`_month_span`)
    between the earliest and latest date collected - never merely the
    first two dates encountered while reading the text in order (spec
    007-extraction-fidelity's own correction of spec 006's original
    before-and-after, first-two-found rule). A span of eleven to thirteen
    months yields `"12"`; five to seven months yields `"6"`; any other
    span yields the exact rounded month count, with a value-free warning
    naming only the computed count. Returns `None` when fewer than two
    distinct dates are found after any surviving label occurrence - the
    caller then leaves `term_months` exactly as its own generator proposed
    (FR-009).

    IMPORTANT 4: when more than two distinct dates survived
    `_find_period_dates`'s own prior-period exclusion (a renewal notice
    date, or a multi-period document this exclusion did not fully
    resolve), a second value-free warning is appended alongside any
    span-range warning `_term_from_span` already produces."""
    dates = _find_period_dates(text)
    if dates is None:
        return None
    date_a, date_b, distinct_count = dates
    span = _month_span(date_a, date_b)
    term = _term_from_span(span)
    warnings: list[str] = []
    if distinct_count > 2:
        warnings.append(_MULTIPLE_DATES_WARNING)
    if term.warning:
        warnings.append(term.warning)
    return TermDerivation(term_months=term.term_months, warning="; ".join(warnings) if warnings else None)


def _resolve_authoritative_term(text: str) -> _TermResolution | None:
    """spec 007-extraction-fidelity, FR-010, FR-011, D2's own restated
    precedence order: an explicit "N-month"/"N month" phrase in `text`
    (spec 006's own `_TERM_RE`) is checked FIRST and, when present, is
    authoritative - amending spec 006 FR-020, which let a date-derived
    value unconditionally replace even a local-model claim that already
    agreed with an explicit phrase in the text. Only when no phrase
    matches does the corrected date-derivation helper
    (`derive_term_from_dates`) run; when neither finds anything, returns
    `None` and the caller's own generator-proposed value passes through
    unexamined by this precedence rule (still subject to the ordinary
    sanity-pass gate like any other figure). Callers pass `text` already
    de-glued (FR-012 through FR-016) so a glued phrase
    (`"Total6month"`-shaped) is detectable here in the first place."""
    phrase_match = _TERM_RE.search(text)
    if phrase_match:
        return _TermResolution(term_months=phrase_match.group(1), warning=None, source="phrase")
    date_derivation = derive_term_from_dates(text)
    if date_derivation is not None:
        return _TermResolution(
            term_months=date_derivation.term_months, warning=date_derivation.warning, source="date"
        )
    return None


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

    # spec 007-extraction-fidelity, FR-010: an explicit "N-month" phrase
    # (checked first, inside _resolve_authoritative_term) still wins here
    # exactly as spec 006 already did; only the date-derivation fallback's
    # own scan/window/span rules changed (FR-006 through FR-009).
    term_resolution = _resolve_authoritative_term(text)
    term_months = term_resolution.term_months if term_resolution else ""
    if not term_months:
        warnings.append("no term detected")
    elif term_resolution.warning:
        warnings.append(term_resolution.warning)

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


# --- De-glue transformation (spec 007-extraction-fidelity, FR-012 through
# FR-016, D3; PRECISION-CORRECTED by BLOCK 1, Opus verifier, 2026-08-30) ---
# The layout-aware converter glues adjacent table cells together at their
# own visual boundary ("Total6month"-shaped, a term label glued to its own
# digit and unit) - this defeats _TERM_RE's own "N-month" phrase match and
# can corrupt a value once it survives into a cached reference.
#
# BLOCK 1 (Opus verifier, 2026-08-30): the original design inserted a space
# at EVERY letter-to-digit or digit-to-letter boundary, unconditionally.
# Measured against the Director's own three real declarations PDFs, this
# also fired INSIDE real identifiers - a 17-character VIN-shaped run and a
# mixed alphanumeric policy/unit-number run both lost every one of their
# own internal digit-letter boundaries, corrupting the identifier itself
# before it could ever reach the sanity pass (an identifier is a text
# field, FR-027, so nothing would have stripped the corrupted result - it
# would have been cached as printed). The corrected rule below is
# precise, not blanket: rules 2/3 fire on a letter<->digit boundary only
# when the SURROUNDING SHAPE looks like a glued label-plus-figure, never
# when it looks like a real identifier.
#
# Rule 1 (lowercase-to-uppercase) is UNCHANGED - a simple, unconditional
# zero-width boundary insertion, since a case transition is a strong,
# unambiguous word-boundary signal with no identifier-corruption risk (a
# VIN, a policy number, and a unit number are conventionally all-uppercase
# or all-digits, never mixed-case).
#
# Known, accepted residual of rule 1 (documented here, in
# contracts/fidelity.md section 3, and in PATTERNS.md): a camel-case
# surname glued into `named_insureds` by the same converter artifact
# ("McDonald"-shaped) renders spaced ("Mc Donald"-shaped) - rule 1 cannot
# distinguish a glued label/word boundary from a genuine internal
# case-transition inside one word, and `named_insureds` is a text field
# read at the Director's own confirmation step, not something this pass
# can safely special-case without a maintained surname exception list
# (which would reopen exactly the "language-specific, open-ended" problem
# D3's own "Alternatives considered" section already rejected for the
# gluing detector itself).
#
# Rules 2/3 (letter<->digit), corrected: a boundary within a maximal
# `[A-Za-z0-9]+` run gains a space only when ALL of:
#   (a) the run's own total letter<->digit transition count is <= 2 - a
#       real identifier (VIN, policy number, spaced unit number) mixes
#       letters and digits far more densely than a glued label-plus-figure
#       ever does, so a run with more than two transitions is left
#       entirely untouched (`_deglue_letter_digit_run` returns it as-is);
#   (b) the digit-side segment at this boundary has length <= 3 - a glued
#       figure's own digit run is short ("6month"); an identifier's digit
#       segment (a VIN's trailing serial, a 7-digit policy suffix) runs
#       long;
#   (c) the letter-side segment at this boundary has length >= 3 - guards
#       a single-letter unit suffix ("4B"-shaped) from being split.
#
# Known, accepted residual (FR-015, unchanged from before this
# correction): a glued word pair sharing NEITHER a case-transition
# boundary nor a qualifying letter/digit boundary (two lowercase words
# glued directly together, e.g. "eachperson"; or a label glued to a long
# digit run that itself looks identifier-shaped, e.g. "Law60500") has no
# boundary signal left in the text for a pure regex to detect, or is
# deliberately left glued because the shape is ambiguous with a real
# identifier - it surfaces unresolved at the Director's own confirmation
# step, the same recourse spec 006 already documents for its own
# unattached standalone deductible-line residual.
_DEGLUE_LOWER_UPPER_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]+")
_LETTER_OR_DIGIT_SEGMENT_RE = re.compile(r"[A-Za-z]+|[0-9]+")
_DEGLUE_MAX_TRANSITIONS = 2
_DEGLUE_MAX_DIGIT_SIDE_LEN = 3
_DEGLUE_MIN_LETTER_SIDE_LEN = 3


def _deglue_letter_digit_run(run: str) -> str:
    """Applies the corrected, precise letter<->digit boundary rule (rules
    2/3 above) to a single maximal alphanumeric `run` - never a blanket
    insertion. Splits `run` into its own alternating letter/digit segments
    (`_LETTER_OR_DIGIT_SEGMENT_RE`); if the run carries more than
    `_DEGLUE_MAX_TRANSITIONS` transitions between segments, returns `run`
    completely unchanged (condition (a) - a real identifier). Otherwise,
    inserts a space at each individual boundary only when the digit-side
    segment there is short (condition (b)) and the letter-side segment
    there is long enough (condition (c))."""
    segments = _LETTER_OR_DIGIT_SEGMENT_RE.findall(run)
    if len(segments) < 2:
        return run
    if (len(segments) - 1) > _DEGLUE_MAX_TRANSITIONS:
        return run
    pieces = [segments[0]]
    for i in range(1, len(segments)):
        prev_seg, curr_seg = segments[i - 1], segments[i]
        if prev_seg[0].isdigit():
            digit_seg, letter_seg = prev_seg, curr_seg
        else:
            digit_seg, letter_seg = curr_seg, prev_seg
        if len(digit_seg) <= _DEGLUE_MAX_DIGIT_SIDE_LEN and len(letter_seg) >= _DEGLUE_MIN_LETTER_SIDE_LEN:
            pieces.append(" ")
        pieces.append(curr_seg)
    return "".join(pieces)


def _deglue_text(text: str) -> str:
    """FR-012 through FR-015, precision-corrected by BLOCK 1: applies rule
    1 (lowercase-to-uppercase, unconditional) as a simple zero-width
    substitution first, then applies the corrected, precise letter<->digit
    rule (`_deglue_letter_digit_run`) to every maximal alphanumeric run of
    the resulting text. Never alters a digit's own value, a currency
    symbol, or any punctuation character already present in the text
    (FR-014) - its only effect is inserting new space characters, and now
    only at boundaries that do not look like a real identifier. `text or
    ""` mirrors this module's own established tolerance for a falsy input
    (`_strip_currency_formatting`, `_source_digit_tokens`)."""
    text = _DEGLUE_LOWER_UPPER_RE.sub(" ", text or "")
    return _ALNUM_RUN_RE.sub(lambda m: _deglue_letter_digit_run(m.group(0)), text)


# --- Layout-aware conversion (spec 006-policy-extraction-v2, FR-001, FR-002, D2) ---

_LAYOUT_CONVERTER_NAME = "pymupdf4llm"
_FALLBACK_CONVERTER_NAME = "pypdf-raw"


@dataclass(frozen=True)
class ConvertedDocument:
    """The in-memory result of the conversion step (data-model.md). Never
    written to disk; never printed on its own - only a candidate built from
    it is ever shown to the Director.

    spec 007-extraction-fidelity, FR-012 through FR-016: `text` is always
    the de-glued form (`_deglue_text`) - `convert_document` (below) applies
    it exactly once, regardless of which path produced the text, before
    this dataclass is ever constructed, so every downstream reader (either
    generator, the term-derivation helper, the sanity pass) sees only
    de-glued text with no wiring of its own."""

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
    v0.0.5 already defines for an unreadable PDF.

    spec 007-extraction-fidelity, FR-016: whichever path produces text, the
    de-glue transformation (`_deglue_text`) runs on it exactly once before
    this function returns - the layout-aware converter's own output and the
    `pypdf` raw-text fallback are both covered by the same single call
    site, so neither path can ever hand a generator, the term-derivation
    helper, or the sanity pass glued text."""
    converter = layout_converter or _default_layout_converter
    try:
        text = converter(str(pdf_path))
    except Exception:
        text = None
    if text:
        return ConvertedDocument(text=_deglue_text(text), converter=_LAYOUT_CONVERTER_NAME)

    factory = reader_factory or pypdf.PdfReader
    fallback_text = _extract_text(Path(pdf_path), factory)
    if not fallback_text:
        return None
    return ConvertedDocument(text=_deglue_text(fallback_text), converter=_FALLBACK_CONVERTER_NAME)


# --- Local-model candidate generation (spec 006-policy-extraction-v2, FR-004, FR-005) ---

_LOCAL_MODEL_PROMPT_TEMPLATE = (
    "You are extracting structured data from an insurance policy declarations "
    "page that has been converted to text below. Read the whole document and "
    "propose a JSON object with exactly these keys: \"insurer\" (string), "
    "\"premium\" (an object with \"term_months\" and \"amount\", both strings), "
    "\"coverages\" (an array of objects, each with \"line\", \"limit\", "
    "\"deductible\", and \"premium\", all strings), \"policy_number\" (string), "
    "\"effective_date\" (string), \"expiration_date\" (string), "
    "\"policy_level_deductibles\" (an array of objects, each with \"label\" and "
    "\"value\", for a policy-wide deductible that does not belong to any single "
    "coverage line), \"asset\" (an object with EITHER an \"address\" string OR "
    "both a \"vehicle\" string and a \"vin\" string), \"named_insureds\" (an "
    "array of name strings), \"excluded_drivers\" (an array of name strings), "
    "\"discounts\" (an array of objects, each with \"label\" and \"value\"), "
    "\"fees\" (an array of objects, each with \"label\" and \"amount\"), and "
    "\"subtotal\" (string). Every figure, date, name, and identifier you "
    "propose MUST be copied verbatim from the document text below - never "
    "invented, estimated, or inferred from outside knowledge. If a value is "
    "not present in the document, use an empty string (or an empty array/"
    "object) for it. Respond with ONLY the JSON object, no other text."
    "\n\nDocument:\n{text}"
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
    num_ctx: int = localllm.DEFAULT_NUM_CTX,
) -> ExtractionCandidate | None:
    """FR-004, FR-005, FR-010: builds the extraction prompt from
    `document.text`, calls `headless/localllm.py`'s transport, and
    constructs an `ExtractionCandidate` from a successful, schema-valid
    response.

    spec 007-extraction-fidelity, FR-010: `_resolve_authoritative_term`
    supplies or overrides `term_months` whenever an explicit "N-month"
    phrase or a policy-period date pair is found in `document.text`'s own
    (already de-glued) text - a value-free note records an override only
    when the model's own claim disagreed with the authoritative value
    (never merely omitted), worded to name whichever source actually won
    (the phrase, or the date derivation) rather than a single fixed
    message for both.

    spec 007-extraction-fidelity, FR-032: before the request is built, a
    length estimate against `document.text` is checked against `num_ctx` -
    when it exceeds the threshold, one value-free warning naming only the
    estimated count and the threshold is added to the returned candidate's
    own `warnings` (the request is still sent; this is a warning, never a
    refusal).

    Returns `None` (never raises) on any failure classification from
    contracts/extraction-v2.md section 1 - the caller falls back to the
    regex-based generator and records the one value-free warning (FR-013)."""
    prompt = _build_extraction_prompt(document.text)
    # IMPORTANT 5 (Opus verifier, 2026-08-30): measure the FULL prompt
    # actually sent to the model - not document.text alone, which
    # under-measures the request by the prompt template's own fixed
    # instructional overhead.
    context_warning = localllm.context_window_warning(prompt, num_ctx)
    try:
        raw = localllm.generate_candidate(
            model=model, url=url, prompt=prompt, transport=transport, timeout=timeout, num_ctx=num_ctx
        )
    except localllm.LocalModelUnavailable:
        return None

    warnings: list[str] = []
    if context_warning:
        warnings.append(context_warning)
    raw_premium = raw.get("premium") if isinstance(raw.get("premium"), dict) else {}
    claimed_term = raw_premium.get("term_months", "") or ""

    term_resolution = _resolve_authoritative_term(document.text)
    if term_resolution is not None:
        if claimed_term and claimed_term != term_resolution.term_months:
            override_note = (
                "term_months derived from an explicit N-month phrase overrode the model's own claim"
                if term_resolution.source == "phrase"
                else "term_months derived from policy-period dates overrode the model's own claim"
            )
            warnings.append(override_note)
        term_months = term_resolution.term_months
        if term_resolution.warning:
            warnings.append(term_resolution.warning)
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
        policy_number=raw.get("policy_number", "") or "",
        effective_date=raw.get("effective_date", "") or "",
        expiration_date=raw.get("expiration_date", "") or "",
        policy_level_deductibles=raw.get("policy_level_deductibles", []),
        asset=raw.get("asset", {}),
        named_insureds=raw.get("named_insureds", []),
        excluded_drivers=raw.get("excluded_drivers", []),
        discounts=raw.get("discounts", []),
        fees=raw.get("fees", []),
        subtotal=raw.get("subtotal", "") or "",
    )


# --- The mechanical sanity pass (spec 006-policy-extraction-v2 FR-017
# through FR-020, D5; corrected by spec 007-extraction-fidelity FR-001
# through FR-005, D1, and extended by FR-022 through FR-027, D5) ---


_DIGIT_RUN_RE = re.compile(r"\d[\d.]*")


def _strip_currency_formatting(value: str) -> str:
    """spec 007-extraction-fidelity, FR-001, FR-002, D1: removes `$` and
    `,` only - whitespace is deliberately NEVER stripped here (amending
    spec 006's own version of this function, which stripped whitespace
    from the proposed side only). A real declarations page states many
    figures as more than one digit run in the same cell - a split
    personal-liability limit written as one line with its own row labels,
    or a policy number rendered with internal spaces between digit groups.
    Stripping whitespace collapsed that composite/spaced value into one
    merged, non-matching blob (research.md Defect A); preserving it here
    lets `_figure_present` (below) tokenize what remains into its own
    separate digit-run tokens, exactly the way the source text is already
    tokenized (`_source_digit_tokens`) - both sides now go through
    identical tokenization. A decimal point also survives, since it is
    significant to the token comparison below (`"753.25"` is a different
    token from `"75325"`)."""
    return re.sub(r"[,$]", "", value or "")


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


def _proposed_digit_tokens(cleaned: str) -> list[str]:
    """spec 007-extraction-fidelity, FR-001, D1: extracts every maximal
    digit-run token from an already-`$`/`,`-stripped proposed value
    (`_strip_currency_formatting`'s own output), normalized the identical
    way `_source_digit_tokens` normalizes the source side. Any surrounding
    letters (a row label, "each person"/"each accident") or whitespace are
    simply never matched by `_DIGIT_RUN_RE` and fall out of the result on
    their own - there is no need to strip them first, only to never let
    them merge two digit runs into one (which stripping whitespace would
    do)."""
    return [_normalize_token(token) for token in _DIGIT_RUN_RE.findall(cleaned)]


def _figure_present(value: str, source_tokens: set[str]) -> bool:
    """spec 007-extraction-fidelity, FR-001 through FR-005, D1 (amends spec
    006's own FIX-FIRST 2 whole-blob check): a proposed figure passes only
    when EVERY digit-run token `_proposed_digit_tokens` extracts from it is
    a member of `source_tokens` - never a single whole-blob string
    comparison, and never substring containment. A split value
    (`"100,000/300,000"`, spec 006's own convention) is still checked as
    its own independent `"/"`-separated parts first, unchanged from spec
    006; what changes is that each part's own cleaned string may now itself
    expand to more than one digit-run token (a composite figure sharing a
    cell with a row label, or a spaced identifier), with every one of them
    required, rather than the whole cleaned part being compared as one
    token. An empty `value` has nothing to check - trivially present. NIT
    10 (Opus verifier, 2026-08-29, unchanged by this correction): a part
    whose cleaned form yields zero digit-run tokens at all (`"N/A"`,
    `"n/a"`) is not a figure - it passes through untouched, since there is
    nothing for a digit-run check to verify; this only applies per
    `"/"`-split part, so a genuinely all-text value never trips the
    "figure absent" warning.

    The hard anti-hallucination invariant (FR-005, spec 006's own
    FIX-FIRST-2 finding) is unchanged by this correction: each extracted
    token is still checked for EXACT set membership, never substring
    containment, so a hallucinated figure sharing only a digit-run suffix
    or prefix with a real, unrelated source figure (`"50,000"` against a
    source that only ever states `"150,000"`) still fails here exactly as
    it already did - this function corrects an asymmetry in how the
    proposed side was tokenized, never the strictness of the comparison
    itself."""
    if not value:
        return True
    for part in value.split("/"):
        cleaned = _strip_currency_formatting(part)
        if not cleaned:
            return False
        tokens = _proposed_digit_tokens(cleaned)
        if not tokens:
            continue  # NIT 10: non-numeric text is not a figure
        if not all(token in source_tokens for token in tokens):
            return False
    return True


# spec 007-extraction-fidelity, FR-026: distinct wording from a figure-strip
# warning, so a reader of the warnings list can tell a date-parse failure
# apart from a stripped-hallucination figure at a glance.
_DATE_PARSE_WARNING_SUFFIX = "could not be parsed as a date and was removed"

# spec 007-extraction-fidelity, BLOCK 2 (Opus verifier, 2026-08-30): the ONE
# precedence table governing term_months, stated identically here, in
# contracts/fidelity.md section 2, and in contracts/fidelity.md section 4 -
# never duplicated with a different order anywhere else in this codebase.
#
#   1. VERIFIED explicit dates - effective_date AND expiration_date both
#      present, both parse, AND both pass the figure gate (their own
#      digit-run tokens are members of source_tokens) - highest precedence.
#   2. An explicit "N-month"/"N month" phrase in the de-glued text.
#   3. The corrected date-window helper (_find_period_dates/
#      derive_term_from_dates).
#   4. Whatever the generator itself proposed, passing through unexamined
#      by this precedence rule (still subject to the ordinary figure gate).
#
# Tier 1 is new in this fix: the original design only ever date-PARSE-
# checked effective_date/expiration_date (FR-026), never verified their
# presence in the source - two internally consistent but entirely
# FABRICATED dates would parse successfully, compute a term, and silently
# outrank even an already-correct phrase or window-derived value, with
# zero warnings. Tier 1 now requires source presence too (the same figure
# gate every other proposed figure already passes through), and a
# disagreement between the winning tier and the next lower tier that
# actually produced a value is surfaced as one value-free warning naming
# both sources' own term VALUES ("12"/"6"-shaped counts are structural,
# not sensitive - never a date or a dollar figure).
_TERM_SOURCE_LABELS = {
    "verified_dates": "verified explicit dates",
    "phrase": "an explicit N-month phrase",
    "date": "policy-period window dates",
    "claim": "the generator's own claim",
}


def _term_disagreement_warning(winner_source: str, winner_value: str, loser_source: str, loser_value: str) -> str:
    return (
        f"term_months from {_TERM_SOURCE_LABELS[winner_source]} ({winner_value}) overrode "
        f"{_TERM_SOURCE_LABELS[loser_source]} ({loser_value})"
    )


def _verify_schema_date(value: str, field_name: str, source_tokens: set[str], warnings: list[str]) -> str:
    """spec 007-extraction-fidelity, BLOCK 2(i): a proposed
    `effective_date`/`expiration_date` must both PARSE (FR-026, unchanged
    wording on failure) AND pass the ordinary figure gate against its own
    digit-run tokens (month/day/year) - a date that parses to a
    syntactically valid calendar date but was never actually stated in the
    source is exactly as fabricated as any other hallucinated figure, and
    is cleared the same way, with a distinctly worded, value-free warning
    naming only the field."""
    if not value:
        return ""
    if _parse_date_token(value) is None:
        warnings.append(f"{field_name} {_DATE_PARSE_WARNING_SUFFIX}")
        return ""
    if not _figure_present(value, source_tokens):
        warnings.append(f"a proposed {field_name} did not appear in the document and was removed")
        return ""
    return value


def apply_sanity_pass(candidate: ExtractionCandidate, source_text: str) -> ExtractionCandidate:
    """FR-017 through FR-020, FR-026 (spec 006); corrected per-token
    literal-match rule (spec 007-extraction-fidelity FR-001 through
    FR-005); extended to gate the schema-extension's own new figure-shaped
    fields and date-parse-check its own two new date fields (FR-022
    through FR-027). Strips any figure absent from `source_text` after
    normalization, replacing it with a value-free warning naming only the
    field (never the value, never a source fragment). Runs against every
    candidate, from either generator, before it ever reaches
    `confirm_candidate` - a regex-derived figure is by construction a
    substring of its own source, so this trivially passes for it (D5's own
    "costs nothing to apply uniformly" rationale).

    `insurer`, each coverage line's own `line` name, `asset`,
    `named_insureds`, `excluded_drivers`, and every entry `label` are text,
    never figures, and are exempt (FR-028, extended by FR-027). `term_months`
    is exempt only when it equals what `_resolve_authoritative_term`
    currently resolves from `source_text` - an explicit de-glued "N-month"
    phrase when one exists, otherwise the corrected date-derivation helper
    (FR-011) - UNLESS `effective_date`/`expiration_date` both parse, in
    which case `term_months` is computed from those two dates instead and
    is never read as a separately proposed value at all (FR-024, the
    highest-precedence source for `term_months` once both dates are
    valid)."""
    source_tokens = _source_digit_tokens(source_text)
    warnings = list(candidate.warnings)

    premium = dict(candidate.premium)
    amount = premium.get("amount", "")
    if amount and not _figure_present(amount, source_tokens):
        premium["amount"] = ""
        warnings.append("a proposed premium amount did not appear in the document and was removed")

    # --- BLOCK 2(i): each proposed date must PARSE and pass the figure -----
    # gate (be verified present in the source) - a merely well-formed but
    # fabricated date is no longer sufficient (see _verify_schema_date).
    effective_date = _verify_schema_date(candidate.effective_date, "effective_date", source_tokens, warnings)
    expiration_date = _verify_schema_date(candidate.expiration_date, "expiration_date", source_tokens, warnings)

    # --- BLOCK 2(ii)-(iv): the ONE precedence table (see the module-level
    # comment above _TERM_SOURCE_LABELS) - tier 1 (verified dates) is
    # computed here; tiers 2/3 (phrase, date-window) are recomputed via
    # _resolve_authoritative_term, exactly as before this fix; tier 4 is
    # whatever the generator itself already proposed.
    verified_dates_term: TermDerivation | None = None
    if effective_date and expiration_date:
        parsed_effective = _parse_date_token(effective_date)
        parsed_expiration = _parse_date_token(expiration_date)
        if parsed_effective is not None and parsed_expiration is not None:
            verified_dates_term = _term_from_span(_month_span(parsed_effective, parsed_expiration))

    claimed_term_months = premium.get("term_months", "")
    term_resolution = _resolve_authoritative_term(source_text)  # tiers 2/3

    if verified_dates_term is not None:
        term_months = verified_dates_term.term_months
        if verified_dates_term.warning:
            warnings.append(verified_dates_term.warning)
        # BLOCK 2(iii): one disagreement warning against the next
        # applicable lower-precedence source that actually produced a
        # value (tier 2/3 first if it has one, else the raw tier-4 claim).
        if term_resolution is not None:
            if term_resolution.term_months != term_months:
                warnings.append(
                    _term_disagreement_warning(
                        "verified_dates", term_months, term_resolution.source, term_resolution.term_months
                    )
                )
        elif claimed_term_months and claimed_term_months != term_months:
            warnings.append(_term_disagreement_warning("verified_dates", term_months, "claim", claimed_term_months))
    else:
        # spec 007-extraction-fidelity, FR-011 (amended by BLOCK 2(iv)):
        # exempt when term_months equals EITHER the phrase-derived or the
        # date-window-derived value (unified into one check via
        # _resolve_authoritative_term, which already prefers the phrase
        # when both exist) - a term matching the verified-dates
        # computation is handled by the branch above, never reaching this
        # ordinary figure-gate check at all.
        term_months = claimed_term_months
        term_exempt = term_resolution is not None and term_months == term_resolution.term_months
        if term_months and not term_exempt and not _figure_present(term_months, source_tokens):
            term_months = ""
            warnings.append("a proposed term_months did not appear in the document and was removed")
    premium["term_months"] = term_months

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

    # --- FR-025: the schema-extension's own new figure-shaped fields, ----
    # gated by the identical corrected check (FR-004).
    policy_number = candidate.policy_number
    if policy_number and not _figure_present(policy_number, source_tokens):
        policy_number = ""
        warnings.append("a proposed policy_number did not appear in the document and was removed")

    policy_level_deductibles = []
    for deductible_entry in candidate.policy_level_deductibles:
        entry = dict(deductible_entry)
        value = entry.get("value", "")
        if value and not _figure_present(value, source_tokens):
            entry["value"] = ""
            label = entry.get("label", "") or "policy-level"
            warnings.append(f"a proposed {label} deductible value did not appear in the document and was removed")
        policy_level_deductibles.append(entry)

    discounts = []
    for discount_entry in candidate.discounts:
        entry = dict(discount_entry)
        value = entry.get("value", "")
        if value and not _figure_present(value, source_tokens):
            entry["value"] = ""
            label = entry.get("label", "") or "discount"
            warnings.append(f"a proposed {label} discount value did not appear in the document and was removed")
        discounts.append(entry)

    fees = []
    for fee_entry in candidate.fees:
        entry = dict(fee_entry)
        amount_value = entry.get("amount", "")
        if amount_value and not _figure_present(amount_value, source_tokens):
            entry["amount"] = ""
            label = entry.get("label", "") or "fee"
            warnings.append(f"a proposed {label} fee amount did not appear in the document and was removed")
        fees.append(entry)

    subtotal = candidate.subtotal
    if subtotal and not _figure_present(subtotal, source_tokens):
        subtotal = ""
        warnings.append("a proposed subtotal did not appear in the document and was removed")

    return ExtractionCandidate(
        insurer=candidate.insurer,
        premium=premium,
        coverages=coverages,
        warnings=warnings,
        policy_number=policy_number,
        effective_date=effective_date,
        expiration_date=expiration_date,
        policy_level_deductibles=policy_level_deductibles,
        # FR-027: text fields, exempt from the sanity pass, passed through
        # unchanged - never touched by any figure check above.
        asset=dict(candidate.asset),
        named_insureds=list(candidate.named_insureds),
        excluded_drivers=list(candidate.excluded_drivers),
        discounts=discounts,
        fees=fees,
        subtotal=subtotal,
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
    FR-055).

    spec 007-extraction-fidelity, FR-019 through FR-021: when `candidate`
    carries one or more warnings, a distinct, explicitly labeled section (a
    count line, then each warning on its own line) prints BEFORE the
    existing header and JSON block - never instead of it, since the JSON
    block already embeds the same `warnings` list (spec 006, unchanged).
    When `candidate` carries zero warnings, this section does not print at
    all."""
    if candidate.warnings:
        print(f"{len(candidate.warnings)} warning(s) from the sanity pass - review before confirming:")
        for warning in candidate.warnings:
            print(f"- {warning}")
    print("Extracted current-policy candidate (your own data, printed for your review):")
    print(json.dumps(candidate.to_dict(), indent=2))
    choice = input_fn("Accept as printed, correct it, or decline? [a/c/d]: ").strip().lower()
    if choice in ("a", "accept"):
        return CurrentPolicy(
            insurer=candidate.insurer,
            premium=dict(candidate.premium),
            coverages=[dict(c) for c in candidate.coverages],
            policy_number=candidate.policy_number,
            effective_date=candidate.effective_date,
            expiration_date=candidate.expiration_date,
            policy_level_deductibles=[dict(d) for d in candidate.policy_level_deductibles],
            asset=dict(candidate.asset),
            named_insureds=list(candidate.named_insureds),
            excluded_drivers=list(candidate.excluded_drivers),
            discounts=[dict(d) for d in candidate.discounts],
            fees=[dict(f) for f in candidate.fees],
            subtotal=candidate.subtotal,
        )
    if choice in ("c", "correct"):
        # IMPORTANT 6 (Opus verifier, 2026-08-30): names the full object
        # printed above (now 14 keys, including warnings and the ten
        # schema-extension fields), not a stale literal "insurer/premium/
        # coverages" list that predates this feature's own extension -
        # CurrentPolicy.from_dict below still only reads the 13 keys it
        # owns (warnings never lives on a confirmed CurrentPolicy).
        raw = input_fn("Paste the corrected JSON document (the same object printed above): ")
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
    always supplies the pipeline's own real values explicitly.

    spec 007-extraction-fidelity, FR-017, FR-018, D4: `warnings` is a
    further additive field, defaulting to an empty list - the sanity pass's
    own warnings list at the moment of confirmation, so a later reader (the
    Director inspecting a cache file directly, or a future report) can see
    what a given confirmed reference actually survived. Lives at the
    `PolicyReference` level, not on the embedded `CurrentPolicy`, since a
    confirmed policy itself never carries warnings - only the surrounding
    reference does (data-model.md)."""

    policy: CurrentPolicy
    asset_key: str
    source_path: str
    confirmed_at: str
    generator: str = "regex-v1"
    converter: str = "pypdf-raw"
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        data = self.policy.to_dict()
        data["source_path"] = self.source_path
        data["confirmed_at"] = self.confirmed_at
        data["generator"] = self.generator
        data["converter"] = self.converter
        data["warnings"] = list(self.warnings)
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


def read_policy_reference_provenance(
    asset_key: str, reports_dir: Path
) -> tuple[str, str, str, str, list] | None:
    """Reads the same cache file `read_policy_reference` reads, but returns
    only its own provenance (`source_path`, `confirmed_at`, `generator`,
    `converter`, `warnings`) rather than the embedded `CurrentPolicy`.
    Exists so the report's provenance footer can satisfy FR-059/FR-024
    (naming the confirmed reference's own source, confirmation date,
    generator, and converter) without `render_report` itself touching the
    filesystem, and without changing `read_policy_reference`'s own
    contracted `CurrentPolicy | None` return shape. `None` under the exact
    same conditions `read_policy_reference` returns `None` (missing or
    unparseable file). `generator`/`converter` default to `"unknown"` when
    absent - true for every cache file written before spec
    006-policy-extraction-v2 existed (data-model.md's own additive-only
    invariant); never treated as an error.

    spec 007-extraction-fidelity, FR-017, FR-018, SC-006: `warnings`
    (the 5th tuple element) defaults to `[]` when absent - true for every
    cache file written before this feature existed - never a `KeyError`,
    the identical additive-only compatibility rule `generator`/`converter`
    already established one feature earlier."""
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
            list(data.get("warnings", [])),
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
