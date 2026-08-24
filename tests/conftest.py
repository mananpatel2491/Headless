"""Shared pytest fixtures: an in-memory vault, a scratch preview directory, and
the local fixture form used by the browser-gated integration tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow "import headless" without installing the package (same convention as
# the Director's Atlassian toolkit): insert the repo root onto sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from headless.secrets import SecretMissing


class FakeVault:
    """In-memory VaultBackend for tests. Never touches the real Keychain or GCP."""

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets: dict[str, str] = dict(secrets or {})

    def get_secret(self, name: str) -> str:
        try:
            return self._secrets[name]
        except KeyError:
            raise SecretMissing(name) from None

    def put_secret(self, name: str, value: str) -> None:
        self._secrets[name] = value

    def delete_secret(self, name: str) -> None:
        self._secrets.pop(name, None)

    def self_test(self) -> bool:
        return True


@pytest.fixture
def fake_vault() -> FakeVault:
    return FakeVault()


@pytest.fixture
def tmp_preview_dir(tmp_path: Path) -> Path:
    return tmp_path / "previews"


@pytest.fixture
def fixture_form_url() -> str:
    form_path = Path(__file__).resolve().parent / "fixtures" / "form.html"
    return form_path.as_uri()


@pytest.fixture
def csp_fixture_url() -> str:
    csp_path = Path(__file__).resolve().parent / "fixtures" / "csp.html"
    return csp_path.as_uri()
