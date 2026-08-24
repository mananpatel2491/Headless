"""The profile registry: the only writable source for typed values (D4, D7).

Loaded once from the vault item named `profile` (a JSON object), addressed
afterwards by dotted path (`identity.pan`, `address.home.line1`). There is no
write API here: the Director edits the document through the vault directly or
a future `scripts/profile_put.py`, out of scope for this feature.
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
            if not isinstance(node, dict) or part not in node:
                raise RegistryMissing(dotted)
            node = node[part]
        if isinstance(node, (dict, list)):
            raise RegistryMissing(dotted)
        return str(node)
