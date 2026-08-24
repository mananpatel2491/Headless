"""Field plans and the typing-source seam.

`Source` and `parse_source` make "the registry is the only writable source" a
type-level property: `Session.fill` (session.py) accepts only a `FieldPlan`,
never a raw string, so there is no API to type an arbitrary value. A
`FieldPlan.source` names exactly one of `registry:<dotted.path>`,
`secret:<item>`, or `literal:<text>`; the session resolves the value itself at
fill-time (D7).
"""

from __future__ import annotations

from dataclasses import dataclass

_KINDS = ("registry", "secret", "literal")


class SourceError(ValueError):
    """Raised when a source string is not `registry:`, `secret:`, or `literal:`."""


@dataclass(frozen=True)
class Source:
    kind: str  # "registry" | "secret" | "literal"
    ref: str


def parse_source(text: str) -> Source:
    """Parse `registry:<dotted>`, `secret:<item>`, or `literal:<text>`.

    Anything else raises SourceError; there is no default kind.
    """
    for kind in _KINDS:
        prefix = f"{kind}:"
        if text.startswith(prefix):
            return Source(kind=kind, ref=text[len(prefix):])
    raise SourceError(f"source {text!r} must start with 'registry:', 'secret:', or 'literal:'")


@dataclass(frozen=True)
class FieldPlan:
    name: str
    selector: str
    source: Source
    kind: str = "fill"  # "fill" | "select" | "check"


def redact(value: str) -> str:
    """Mask `value` to its last two characters, or fully mask short values."""
    if len(value) < 3:
        return "****"
    return "****" + value[-2:]


def resolve_source(source: Source, vault, registry) -> str:
    """Resolve a Source to its actual value.

    This is the one place in the package a raw secret or registry value is
    produced. `session.py` (fill) and `errand.py` (preview/record building)
    both call through here instead of re-implementing the dispatch, so there
    is exactly one code path to audit for a leak. Callers must never print or
    log the result directly; `preview.py` masks it before it reaches an
    artifact.
    """
    if source.kind == "registry":
        return registry.get(source.ref)
    if source.kind == "secret":
        return vault.get_secret(source.ref)
    if source.kind == "literal":
        return source.ref
    raise ValueError(f"unknown source kind: {source.kind!r}")
