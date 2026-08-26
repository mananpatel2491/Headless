"""The deterministic comparison engine (spec 005-insurance-quote-comparison,
User Story 3, research.md D5/D10/D18).

Pure functions only - no file I/O, no vault access, no browser, and no LLM
call anywhere in this module (spec FR-020). Every parse and comparison uses
Python's `Decimal` type exclusively, never `float` (spec FR-067(e)) - this is
what makes `build_comparison`'s byte-identical-output invariant
(data-model.md) achievable in practice, not only in principle.

Line-classification combination rule (an implementer decision this module
documents explicitly, since FR-067(c)/(d) define the limit and deductible
comparisons independently but spec.md does not state how the two combine
into one line-level verdict): a "worse" sub-metric always wins - a coverage
regression is a regression whichever figure carries it, and this is what
keeps FR-016's "no coverage line worse than current always outranks a
cheaper quote that has one" rule meaningful regardless of which of limit or
deductible carried the regression. "not_comparable" wins next - a line is
never silently called equal or better when part of its own comparison could
not be parsed. "better" wins over "equal" otherwise. See `_combine`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from headless.capture import CurrentPolicy, QuoteCapture

# Coverage-line alias table (research.md D10): hand-authored, not learned,
# fuzzy-matched, or LLM-generated. Maps a normalized key to the phrasings a
# real insurer's declarations page or quote page might use for it. Extend
# by hand whenever a real insurer's own wording does not already match an
# entry here - never by adding a fuzzy-matching or inference mechanism.
_ALIASES: dict[str, tuple[str, ...]] = {
    "bodily_injury": ("bodily injury liability", "bodily injury", "bi"),
    "property_damage": ("property damage liability", "property damage", "pd"),
    "collision": ("collision",),
    "comprehensive": ("comprehensive", "comp"),
    "uninsured_motorist": ("uninsured motorist", "underinsured motorist", "um", "uim"),
    "medical_payments": ("medical payments", "personal injury protection", "pip", "medpay"),
}


def normalize_line(name: str) -> str:
    """Normalize a coverage-line name (from a capture or `current_policy`)
    to its alias-table key (spec FR-017). An unrecognized name normalizes
    to its own lower-cased, stripped form - still a stable, deterministic
    key, just not one this table has a synonym entry for yet."""
    lowered = (name or "").strip().lower()
    for key, aliases in _ALIASES.items():
        if lowered == key or lowered in aliases:
            return key
    return lowered


# --- FR-067(a): amount and term parsing -------------------------------------


def _parse_amount(raw: str | None) -> Decimal | None:
    """Strip currency symbols, commas, and spaces, then parse as a decimal
    number (FR-067(a)). `None` on any parse failure, never a crash.

    FIX-FIRST 5 (Opus verifier, 2026-08-26): `Decimal("nan")`,
    `Decimal("Infinity")`, and `Decimal("inf")` all parse successfully -
    `Decimal` itself never raises `InvalidOperation` for these, since they
    are valid IEEE 754-style special values, not malformed input. Left
    unchecked, one of these reaching `build_comparison` (e.g. a captured
    quote's premium literally reading "NaN" or "Infinity") would raise
    `InvalidOperation` later, inside a comparison or a `.quantize()` call,
    crashing the whole comparison run instead of ranking that one quote
    last as "premium not comparable" - `scripts/quote_compare.py` would
    exit without ever writing a report, which is exactly the "a report
    must still be produced" guarantee (FR-025) this function's own callers
    depend on. `is_finite()` rejects both classes explicitly.
    """
    if not raw:
        return None
    cleaned = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return value


def _parse_term_months(raw: str | None) -> int | None:
    """A positive integer only (FR-067(a)); `None` on any parse failure."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    return value if value > 0 else None


def _premium_ok(premium: dict) -> tuple[bool, Decimal | None]:
    amount = _parse_amount(premium.get("amount"))
    term = _parse_term_months(premium.get("term_months"))
    if amount is None or term is None:
        return False, None
    monthly = (amount / Decimal(term)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return True, monthly


# --- FR-067(c): limit comparison --------------------------------------------


def _parse_limit(raw: str | None) -> tuple[int, ...] | None:
    """Split on `"/"`, strip `$`/commas from each part, multiply a part by
    1000 when it ends in `k`/`K` (FR-067(c)). `None` on any parse failure."""
    if not raw:
        return None
    values: list[int] = []
    for part in raw.split("/"):
        cleaned = part.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        multiplier = 1
        if cleaned[-1] in ("k", "K"):
            multiplier = 1000
            cleaned = cleaned[:-1]
        if not cleaned.isdigit():
            return None
        values.append(int(cleaned) * multiplier)
    return tuple(values)


def _compare_limits(current: str | None, captured: str | None) -> str:
    """"better", "equal", "worse", or "not_comparable" (FR-067(c)). Two
    limits compare only when their tuples share arity; a different arity or
    an unparseable side is "not_comparable", its own class."""
    current_tuple = _parse_limit(current)
    captured_tuple = _parse_limit(captured)
    if current_tuple is None or captured_tuple is None:
        return "not_comparable"
    if len(current_tuple) != len(captured_tuple):
        return "not_comparable"
    if any(c < cur for c, cur in zip(captured_tuple, current_tuple)):
        return "worse"
    if all(c == cur for c, cur in zip(captured_tuple, current_tuple)):
        return "equal"
    return "better"


# --- FR-067(d): deductible comparison ---------------------------------------


def _compare_deductible(current: str | None, captured: str | None) -> str:
    """Parses the same way as an amount (FR-067(a)'s stripping rule) to a
    single number; a LOWER parsed deductible is better. An empty deductible
    on either side is "not_comparable" (FR-067(d))."""
    if not current or not captured:
        return "not_comparable"
    current_amount = _parse_amount(current)
    captured_amount = _parse_amount(captured)
    if current_amount is None or captured_amount is None:
        return "not_comparable"
    if captured_amount < current_amount:
        return "better"
    if captured_amount > current_amount:
        return "worse"
    return "equal"


_COMBINE_PRIORITY = ("worse", "not_comparable", "better", "equal")


def _combine(limit_class: str, deductible_class: str) -> str:
    for candidate in _COMBINE_PRIORITY:
        if limit_class == candidate or deductible_class == candidate:
            return candidate
    return "equal"  # unreachable: every branch above is exhaustive


def classify_line(current_coverage: dict | None, captured_coverage: dict | None) -> str:
    """Classify one normalized coverage line for one captured quote against
    `current_policy` (spec FR-018). "missing" exactly when
    `captured_coverage` is `None` or its own `limit` is an empty string -
    the captured field's value was never found. A current-policy-only
    comparison is never attempted when `current_coverage is None` (a line
    only a captured quote has, that `current_policy` lacks): that line's
    own value is present but there is nothing to compare it against, so it
    classifies "not_comparable" rather than a guessed better/worse/equal.
    """
    if captured_coverage is None or not captured_coverage.get("limit"):
        return "missing"
    if current_coverage is None:
        return "not_comparable"
    limit_class = _compare_limits(current_coverage.get("limit"), captured_coverage.get("limit"))
    deductible_class = _compare_deductible(
        current_coverage.get("deductible"), captured_coverage.get("deductible")
    )
    return _combine(limit_class, deductible_class)


@dataclass(frozen=True)
class RankedQuote:
    insurer: str
    capture: QuoteCapture
    line_classifications: dict
    normalized_premium: str
    premium_comparable: bool


@dataclass(frozen=True)
class ComparisonResult:
    ranked_quotes: list
    recommended: RankedQuote | None
    rule_trail: str
    has_current_policy: bool


def _all_line_keys(current_policy: CurrentPolicy | None, captures: dict[str, QuoteCapture]) -> list[str]:
    keys: set[str] = set()
    if current_policy is not None:
        for coverage in current_policy.coverages:
            keys.add(normalize_line(coverage.get("line", "")))
    for capture in captures.values():
        for coverage in capture.coverages:
            keys.add(normalize_line(coverage.get("line", "")))
    return sorted(keys)


def _sort_key(rq: RankedQuote, has_current_policy: bool):
    worse = 0
    missing = 0
    if has_current_policy:
        worse = 1 if any(v == "worse" for v in rq.line_classifications.values()) else 0
        missing = sum(1 for v in rq.line_classifications.values() if v == "missing")
    premium_rank = 0 if rq.premium_comparable else 1
    premium_value = Decimal(rq.normalized_premium) if rq.premium_comparable else Decimal("Infinity")
    return (premium_rank, worse, premium_value, missing, rq.insurer)


def current_policy_normalized_premium(current_policy: CurrentPolicy) -> str | None:
    """The current policy's own monthly-equivalent premium, computed by the
    exact same FR-067(a)/(b) rules a captured quote's own
    `RankedQuote.normalized_premium` already uses (FIX-FIRST 4, Opus
    verifier, 2026-08-26) - so a rule trail or a report table can show the
    current and a captured premium like-for-like at a glance, never a raw
    N-month figure sitting unlabelled beside a monthly one. `None` when
    `current_policy`'s own premium fails FR-067(a)'s own parsing rule -
    the same "not comparable" outcome a captured quote's premium can have.
    """
    comparable, monthly = _premium_ok(current_policy.premium)
    return str(monthly) if comparable else None


def current_premium_label(current_policy: CurrentPolicy | None) -> str:
    """A human-readable, term-labelled rendering of `current_policy`'s own
    raw premium, with its own monthly-equivalent figure alongside when it
    parses (FIX-FIRST 4): `"$600.00 per 6 months ($100.00/mo equivalent)"`.
    Shared by `_build_rule_trail` (this module) and `headless/report.py`'s
    premium row, so the two can never drift into two different renderings
    of the same figure. `"unknown"` when there is no current policy at all
    (the caller should not normally reach this branch when
    `has_current_policy` is `False`, but degrading here rather than
    raising keeps this a pure formatting helper with no error path of its
    own)."""
    if current_policy is None:
        return "unknown"
    amount = current_policy.premium.get("amount", "")
    term = current_policy.premium.get("term_months", "")
    label = f"${amount} per {term} months" if term else f"${amount}"
    monthly = current_policy_normalized_premium(current_policy)
    if monthly is not None:
        label += f" (${monthly}/mo equivalent)"
    return label


def _build_rule_trail(top: RankedQuote, current_policy: CurrentPolicy | None, has_current_policy: bool) -> str:
    if not top.premium_comparable:
        return f"{top.insurer}: premium not comparable (could not parse amount/term); ranked last of the available quotes."
    if not has_current_policy:
        return (
            "no current-policy reference on file; ranked by monthly-equivalent premium alone. "
            f"recommended because: {top.insurer} has the lowest monthly-equivalent premium, "
            f"${top.normalized_premium}/mo."
        )
    worse_count = sum(1 for v in top.line_classifications.values() if v == "worse")
    current_label = current_premium_label(current_policy)
    if worse_count == 0:
        return (
            "recommended because: every line at least matches current, premium "
            f"${top.normalized_premium}/mo vs current {current_label}."
        )
    return (
        f"recommended because: lowest premium among available quotes, ${top.normalized_premium}/mo "
        f"(note: {worse_count} coverage line(s) worse than current, current {current_label})."
    )


def build_comparison(
    current_policy: CurrentPolicy | None, captures: dict[str, QuoteCapture]
) -> ComparisonResult:
    """Pure output of the comparison engine (data-model.md). `current_policy`
    is `None` exactly when no confirmed current-policy reference existed for
    the targeted asset (FR-046) - a normal, non-error input, not a sentinel
    the caller has to special-case around this function's boundary.
    `captures`' keys are always iterated in sorted order (never Python's own
    dict-insertion order) so the result is deterministic regardless of how
    the caller built the dict (data-model.md's own determinism invariant).
    """
    has_current_policy = current_policy is not None
    line_keys = _all_line_keys(current_policy, captures)
    current_by_line = (
        {normalize_line(c.get("line", "")): c for c in current_policy.coverages}
        if current_policy is not None
        else {}
    )

    ranked: list[RankedQuote] = []
    for insurer in sorted(captures):
        capture = captures[insurer]
        premium_comparable, monthly = _premium_ok(capture.premium)
        classifications: dict[str, str] = {}
        if has_current_policy:
            captured_by_line = {normalize_line(c.get("line", "")): c for c in capture.coverages}
            for key in line_keys:
                classifications[key] = classify_line(current_by_line.get(key), captured_by_line.get(key))
        normalized_premium_str = str(monthly) if premium_comparable else "premium not comparable"
        ranked.append(
            RankedQuote(
                insurer=insurer,
                capture=capture,
                line_classifications=classifications,
                normalized_premium=normalized_premium_str,
                premium_comparable=premium_comparable,
            )
        )

    ranked.sort(key=lambda rq: _sort_key(rq, has_current_policy))

    if not ranked:
        return ComparisonResult(
            ranked_quotes=[], recommended=None, rule_trail="", has_current_policy=has_current_policy
        )

    top = ranked[0]
    rule_trail = _build_rule_trail(top, current_policy, has_current_policy)
    return ComparisonResult(
        ranked_quotes=ranked, recommended=top, rule_trail=rule_trail, has_current_policy=has_current_policy
    )
