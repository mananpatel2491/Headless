"""QuoteCapture/CurrentPolicy shapes, `feature_configs.insurance.companies`
parsing, and the capture file family (spec 005-insurance-quote-comparison,
data-model.md). No vault access, no browser, no LLM call anywhere in this
module - every function here is pure or touches only the local filesystem
under `reports/`.

There is no `parse_current_policy` here: `current_policy` is deleted from
`profile` entirely (research.md D3, revised twice); a confirmed
`CurrentPolicy` reference is built only by `headless/policydoc.py`'s
extraction-and-confirmation path.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


class QuoteInputError(ValueError):
    """Raised by `parse_companies` when `profile`'s `feature_configs.
    insurance.companies` sub-object is missing or malformed - the same
    position-only-message shape `ProfileError` already established for
    `profile`'s own top-level JSON validity (spec 001). Never echoes
    `profile`'s own content, only which piece is missing or wrong-shaped
    (spec FR-012)."""


def parse_companies(raw: object) -> list[str]:
    """Validate the already-parsed
    `profile["feature_configs"]["insurance"]["companies"]` fragment (spec
    FR-011, FR-012, data-model.md). The caller navigates there itself
    (`profile_doc.get("feature_configs", {}).get("insurance", {}).
    get("companies")`, contracts section 4) so a missing `feature_configs`
    or a missing `feature_configs.insurance` collapses to the same `None`
    this function receives - the refusal still names the full dotted path,
    never `profile`'s own content, satisfying FR-012 without this function
    needing to know which level was actually absent.

    A valid, empty array (`[]`) is not an error - it means the Director has
    not yet listed any insurer to compare (data-model.md's own "empty is a
    valid, unremarkable state" precedent, spec 004).
    """
    path = "feature_configs.insurance.companies"
    if raw is None:
        raise QuoteInputError(f"profile.{path} is missing")
    if not isinstance(raw, list):
        raise QuoteInputError(f"profile.{path} must be a JSON array")
    for entry in raw:
        if not isinstance(entry, str):
            raise QuoteInputError(f"profile.{path} must contain only strings")
    return list(raw)


@dataclass(frozen=True)
class CurrentPolicy:
    """The confirmed current-policy reference shape (data-model.md). Built
    only by `headless/policydoc.py`'s extraction-and-confirmation path -
    never parsed from `profile` directly."""

    insurer: str
    premium: dict  # {"term_months": str, "amount": str}
    coverages: list  # [{"line", "limit", "deductible": "", "premium": ""}]

    def to_dict(self) -> dict:
        return {
            "insurer": self.insurer,
            "premium": dict(self.premium),
            "coverages": [dict(c) for c in self.coverages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CurrentPolicy":
        return cls(
            insurer=data["insurer"],
            premium=dict(data["premium"]),
            coverages=[dict(c) for c in data.get("coverages", [])],
        )


@dataclass(frozen=True)
class QuoteCapture:
    """The structured record one insurer's successful `CaptureStep`
    produces (data-model.md). `package` is `None` when the funnel has no
    tiering at all, or names the funnel's own pre-selected (default) tier
    when it does - never a tier the walk itself chose (spec FR-014)."""

    insurer: str
    fetched_at: str
    premium: dict
    coverages: list
    source_url: str
    package: str | None = None

    def to_dict(self) -> dict:
        return {
            "insurer": self.insurer,
            "fetched_at": self.fetched_at,
            "premium": dict(self.premium),
            "coverages": [dict(c) for c in self.coverages],
            "source_url": self.source_url,
            "package": self.package,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuoteCapture":
        return cls(
            insurer=data["insurer"],
            fetched_at=data["fetched_at"],
            premium=dict(data.get("premium", {})),
            coverages=[dict(c) for c in data.get("coverages", [])],
            source_url=data.get("source_url", ""),
            package=data.get("package"),
        )


_COVERAGE_SUFFIXES = ("limit", "deductible", "premium")


def assemble_capture(
    insurer: str,
    source_url: str,
    fetched_at: str,
    raw_fields: dict,
    package: str | None = None,
) -> QuoteCapture:
    """Parse `Session.capture()`'s flat `raw_fields` mapping into a
    `QuoteCapture`, using data-model.md's fixed vocabulary of dotted field
    keys: `"premium.amount"`, `"premium.term_months"`, and
    `"coverage.<line-slug>.limit"` / `".deductible"` / `".premium"`. A
    `raw_fields` key outside this vocabulary is ignored (forward-compatible:
    a future insurer's walk can capture extra diagnostic fields without this
    function needing to change first). This function never raises for a
    shape `Session.capture()` itself cannot produce - a vocabulary key
    present in `extractors` but absent from `raw_fields` is treated the same
    as an empty-string value.
    """
    premium = {
        "amount": raw_fields.get("premium.amount", ""),
        "term_months": raw_fields.get("premium.term_months", ""),
    }
    lines: dict[str, dict[str, str]] = {}
    for key, value in raw_fields.items():
        if not key.startswith("coverage."):
            continue
        rest = key[len("coverage."):]
        parts = rest.rsplit(".", 1)
        if len(parts) != 2:
            continue
        line_slug, suffix = parts
        if suffix not in _COVERAGE_SUFFIXES:
            continue
        entry = lines.setdefault(
            line_slug, {"line": line_slug, "limit": "", "deductible": "", "premium": ""}
        )
        entry[suffix] = value
    coverages = [lines[slug] for slug in sorted(lines)]
    return QuoteCapture(
        insurer=insurer,
        fetched_at=fetched_at,
        premium=premium,
        coverages=coverages,
        source_url=source_url,
        package=package,
    )


def reports_dir_for(config) -> Path:
    """Where `reports/` resolves for this run: a sibling directory to
    `config.preview_dir` (research.md D4) - no new environment variable, no
    new CLI flag. Production's default `preview_dir`
    (`<repo_root>/previews`) makes this `<repo_root>/reports`; a test
    overriding `--preview-dir` to a tmp path gets an equally isolated
    `reports/` beside it, never the real repository tree.
    """
    return Path(config.preview_dir).parent / "reports"


def _filesystem_safe(fetched_at: str) -> str:
    """A filesystem-safe, still-chronologically-sortable slug derived from
    an ISO 8601 UTC timestamp (`fetched_at`'s own format, `.isoformat()`) -
    strips every character that is not a digit or a letter, so `:`/`.`/`+`
    (all disallowed or awkward on some filesystems) never reach a
    filename."""
    return re.sub(r"[^0-9A-Za-z]", "", fetched_at)


def write_capture(capture: QuoteCapture, reports_dir: Path) -> Path:
    """Writes `reports_dir/captures/<insurer>-<fetched_at, filesystem-safe>.json`,
    creating `captures/` if needed. Captures accumulate - this call never
    overwrites or deletes an earlier capture for the same insurer.

    Opens at mode `0600` before any content lands (NIT 6, Opus verifier,
    2026-08-26), mirroring `scripts/vault.py`'s and `headless/session.py`'s
    own `os.open(..., 0o600)` pattern - `reports/` is vault-grade local
    data (`CLAUDE.md`'s Secrets section) the same way `previews/` already
    is, and a captured premium or coverage limit should never sit briefly
    world/group-readable at the process's default umask before a
    write-then-chmod narrows it after the fact.
    """
    captures_dir = Path(reports_dir) / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    stamp = _filesystem_safe(capture.fetched_at)
    path = captures_dir / f"{capture.insurer}-{stamp}.json"
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # missing file (the ordinary case - captures accumulate) or Windows.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(capture.to_dict(), indent=2))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows: no-op, mirrors scripts/vault.py's own FR-022 convention.
    return path


def read_freshest_capture(insurer: str, reports_dir: Path) -> QuoteCapture | None:
    """Globs `reports_dir/captures/<insurer>-*.json`, sorts by the timestamp
    embedded in the filename (not filesystem mtime, which a copy or a
    backup tool could disturb), and parses the newest one. `None` when no
    capture file exists yet for that insurer, or the newest one fails to
    parse - the caller treats `None` as "capture failed / no data yet"
    (spec FR-024), never as an error."""
    captures_dir = Path(reports_dir) / "captures"
    if not captures_dir.exists():
        return None
    matches = sorted(captures_dir.glob(f"{insurer}-*.json"))
    if not matches:
        return None
    newest = matches[-1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
        return QuoteCapture.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None
