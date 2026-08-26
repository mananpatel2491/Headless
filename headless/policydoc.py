"""Policy PDF extraction, Director confirmation, and the `reports/policy/`
cache (spec 005-insurance-quote-comparison, User Story 3, research.md D15).

`current_policy` is not hand-typed; it is derived, per insured asset, from
that asset's own `policy_doc` PDF, deterministically extracted via `pypdf`
and then Director-confirmed before it can ever be compared against. No LLM
call exists anywhere in this module (spec FR-051) - the same constitutional
rule the comparison engine already follows (`headless/compare.py`), extended
here to cover extraction as well.

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
from pathlib import Path
from typing import Callable

import pypdf

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


def _extract_text(pdf_path: Path, reader_factory: Callable[[str], object]) -> str | None:
    try:
        reader = reader_factory(str(pdf_path))
        pages = getattr(reader, "pages", [])
        text = "\n".join((page.extract_text() or "") for page in pages)
    except Exception:
        return None
    return text or None


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

    warnings: list[str] = []

    insurer_match = _INSURER_RE.search(text)
    insurer = insurer_match.group(1).strip() if insurer_match else ""
    if not insurer:
        warnings.append("no insurer detected")

    term_match = _TERM_RE.search(text)
    term_months = term_match.group(1) if term_match else ""
    if not term_months:
        warnings.append("no term detected")

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
    it is cached under (data-model.md)."""

    policy: CurrentPolicy
    asset_key: str
    source_path: str
    confirmed_at: str

    def to_dict(self) -> dict:
        data = self.policy.to_dict()
        data["source_path"] = self.source_path
        data["confirmed_at"] = self.confirmed_at
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


def read_policy_reference_provenance(asset_key: str, reports_dir: Path) -> tuple[str, str] | None:
    """Reads the same cache file `read_policy_reference` reads, but returns
    only its own provenance (`source_path`, `confirmed_at`) rather than the
    embedded `CurrentPolicy`. Exists so the report's provenance footer can
    satisfy FR-059 (naming the confirmed reference's own source and
    confirmation date) without `render_report` itself touching the
    filesystem, and without changing `read_policy_reference`'s own
    contracted `CurrentPolicy | None` return shape. `None` under the exact
    same conditions `read_policy_reference` returns `None` (missing or
    unparseable file)."""
    path = Path(reports_dir) / "policy" / f"{asset_key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data["source_path"], data["confirmed_at"])
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def is_excluded(asset: dict) -> bool:
    """`True` when `asset.get("currently_insured") == "n/a"` or
    `asset.get("policy_doc") == "n/a"` (spec FR-061). One function, two
    callers (`scripts/policy_extract.py`, `scripts/quote_compare.py`), so
    the sentinel's own meaning is defined in exactly one place. Never
    mutates its input."""
    return asset.get("currently_insured") == "n/a" or asset.get("policy_doc") == "n/a"
