"""The profile registry: the only writable source for typed values (D4, D7).

Loaded once from the vault item named `profile` (a JSON object), addressed
afterwards by dotted path (`identity.pan`, `address.home.line1`). There is no
write API here: the Director edits the document through the vault directly or
a future `scripts/profile_put.py`, out of scope for this feature.

Type-discriminated array addressing (v0.0.5, spec 005-insurance-quote-comparison,
research.md D13): the Director's real `profile` document holds `identities`,
`addresses`, and `vehicles` as JSON arrays, each element carrying a `type`
field. When traversal reaches a list-valued node, the next path segment
selects the unique element whose `type` field equals that segment exactly;
traversal then continues from that element as though it had been reached
directly. Zero matches raise the existing `RegistryMissing`; more than one
match raises the new `RegistryAmbiguous` below. This is new, general
framework capability - not specific to insurance or to Progressive - so it
lives in this module's own existing traversal, not a parallel resolver.
"""

from __future__ import annotations

import json

from headless.secrets import VaultBackend


class RegistryMissing(KeyError):
    """Raised when a dotted path is absent, or resolves to a non-scalar value."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path

    def __str__(self) -> str:
        return f"registry path {self.path!r} not found or not a scalar"


class RegistryAmbiguous(KeyError):
    """Raised when a dotted path's next segment matches more than one list
    element's `type` field (spec FR-042, research.md D13). Value-free by
    construction: names only the path and the fact of duplication, never
    either matched element's own field content - two elements sharing a
    `type` value could, in principle, differ in every other field, and
    echoing either one's content back would leak whichever was picked
    first."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path

    def __str__(self) -> str:
        return f"registry path {self.path!r} matches more than one element by type"


class ProfileError(ValueError):
    """Raised when the `profile` vault item is not valid JSON, or not a JSON
    object. The message is position-only (the vault item's name plus
    `json.JSONDecodeError`'s own line/column/char report) - it never echoes
    document content, so it is safe for `Errand.run` to print (N10)."""


class ProfileRegistry:
    def __init__(self, document: dict) -> None:
        self._document = document

    @classmethod
    def load(cls, vault: VaultBackend, item: str = "profile") -> "ProfileRegistry":
        raw = vault.get_secret(item)
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProfileError(f"vault item {item!r} is not valid JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ProfileError(f"vault item {item!r} must be a JSON object")
        return cls(document)

    def get(self, dotted: str) -> str:
        node: object = self._document
        for part in dotted.split("."):
            if isinstance(node, list):
                # Type-discriminated array addressing (FR-040 through
                # FR-044, research.md D13): an element with no `type` field
                # is never a match candidate (el.get("type") is None, which
                # can never equal a real path segment string) - silently
                # excluded, not an error (FR-043).
                candidates = [
                    element
                    for element in node
                    if isinstance(element, dict) and element.get("type") == part
                ]
                if len(candidates) == 0:
                    raise RegistryMissing(dotted)
                if len(candidates) > 1:
                    raise RegistryAmbiguous(dotted)
                node = candidates[0]
                continue
            if not isinstance(node, dict) or part not in node:
                raise RegistryMissing(dotted)
            node = node[part]
        if isinstance(node, (dict, list)):
            raise RegistryMissing(dotted)
        return str(node)
