"""Unit tests for headless/secrets.py: FakeVault, the exact `security` argv
KeychainBackend builds (subprocess patched, no real Keychain touched), the
GcpBackend NotFound -> SecretMissing mapping with a fake client, and open_vault
backend selection with proof that the keychain path never imports google.cloud
(D3).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from headless.config import load_config
from headless.secrets import GcpBackend, KeychainBackend, SecretMissing, open_vault

# FakeVault comes from the fake_vault fixture (tests/conftest.py) so every test
# module shares one class identity instead of re-importing it.


# --- FakeVault -----------------------------------------------------------


def test_fake_vault_put_get_delete(fake_vault):
    fake_vault.put_secret("item", "value")
    assert fake_vault.get_secret("item") == "value"
    fake_vault.delete_secret("item")
    with pytest.raises(SecretMissing):
        fake_vault.get_secret("item")


def test_fake_vault_missing_names_the_item(fake_vault):
    with pytest.raises(SecretMissing) as exc_info:
        fake_vault.get_secret("nope")
    assert exc_info.value.name == "nope"


def test_fake_vault_self_test(fake_vault):
    assert fake_vault.self_test() is True


# --- KeychainBackend -------------------------------------------------------


class _FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_keychain_backend_get_secret_argv(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0, stdout="hunter2\n")

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    backend = KeychainBackend("headless")
    value = backend.get_secret("my-item")

    assert value == "hunter2"
    assert calls == [["security", "find-generic-password", "-a", "headless", "-s", "my-item", "-w"]]


def test_keychain_backend_put_secret_argv_never_prints_value(monkeypatch, capsys):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    backend = KeychainBackend("headless")
    backend.put_secret("my-item", "hunter2-secret")

    assert calls == [
        ["security", "add-generic-password", "-a", "headless", "-s", "my-item", "-w", "hunter2-secret", "-U"]
    ]
    captured = capsys.readouterr()
    assert "hunter2-secret" not in captured.out
    assert "hunter2-secret" not in captured.err


def test_keychain_backend_delete_secret_argv(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    KeychainBackend("headless").delete_secret("my-item")

    assert calls == [["security", "delete-generic-password", "-a", "headless", "-s", "my-item"]]


def test_keychain_backend_missing_item_maps_to_secret_missing(monkeypatch):
    def fake_run(argv, **kwargs):
        return _FakeCompleted(returncode=44, stdout="")

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    backend = KeychainBackend("headless")
    with pytest.raises(SecretMissing) as exc_info:
        backend.get_secret("absent-item")
    assert exc_info.value.name == "absent-item"


def test_keychain_backend_put_secret_write_failure_never_leaks_value(monkeypatch):
    raw_value = "hunter2-super-secret-XY"

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(returncode=51, cmd=argv)

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    backend = KeychainBackend("headless")
    with pytest.raises(RuntimeError) as exc_info:
        backend.put_secret("my-item", raw_value)

    assert raw_value not in str(exc_info.value)
    assert "my-item" in str(exc_info.value)
    assert "51" in str(exc_info.value)
    assert exc_info.value.__cause__ is None  # `from None`: original CalledProcessError not chained


def test_keychain_backend_delete_secret_write_failure_is_runtime_error(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(returncode=51, cmd=argv)

    monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)
    backend = KeychainBackend("headless")
    with pytest.raises(RuntimeError) as exc_info:
        backend.delete_secret("my-item")
    assert "my-item" in str(exc_info.value)


# --- GcpBackend (fake client, no google.cloud installed) -------------------


class NotFound(Exception):
    """Named to match google.api_core.exceptions.NotFound by class name, since
    GcpBackend detects it by name (no import) to stay usable without the SDK
    installed."""


class _FakeGcpClient:
    def __init__(self, secrets: dict[str, str] | None = None, list_secrets_raises: bool = False):
        self.secrets = dict(secrets or {})
        self.accessed = []
        self.list_secrets_calls = []
        self._list_secrets_raises = list_secrets_raises

    def access_secret_version(self, name: str):
        self.accessed.append(name)
        secret_name = name.split("/secrets/")[1].split("/versions/")[0]
        if secret_name not in self.secrets:
            raise NotFound(name)

        class _Payload:
            def __init__(self, data: bytes):
                self.data = data

        class _Response:
            def __init__(self, data: bytes):
                self.payload = _Payload(data)

        return _Response(self.secrets[secret_name].encode("utf-8"))

    def list_secrets(self, request):
        self.list_secrets_calls.append(request)
        if self._list_secrets_raises:
            raise RuntimeError("simulated list_secrets failure (e.g. no permission / no project)")
        return []


def test_gcp_backend_construction_does_not_import_google_cloud():
    # No client is injected, and we never call a method that needs one:
    # constructing GcpBackend must not require google-cloud-secret-manager.
    GcpBackend("my-project")
    assert "google.cloud.secretmanager" not in sys.modules


def test_gcp_backend_get_secret_reads_latest_version():
    client = _FakeGcpClient({"my-secret": "the-value"})
    backend = GcpBackend("my-project", client=client)
    assert backend.get_secret("my-secret") == "the-value"
    assert client.accessed == ["projects/my-project/secrets/my-secret/versions/latest"]


def test_gcp_backend_not_found_maps_to_secret_missing():
    client = _FakeGcpClient({})
    backend = GcpBackend("my-project", client=client)
    with pytest.raises(SecretMissing) as exc_info:
        backend.get_secret("absent-secret")
    assert exc_info.value.name == "absent-secret"


def test_gcp_backend_self_test_performs_a_real_list_secrets_call():
    # NIT 18: self_test must not just construct a client, it must exercise it.
    client = _FakeGcpClient()
    backend = GcpBackend("my-project", client=client)
    assert backend.self_test() is True
    assert client.list_secrets_calls == [{"parent": "projects/my-project", "page_size": 1}]


def test_gcp_backend_self_test_false_on_list_secrets_failure():
    client = _FakeGcpClient(list_secrets_raises=True)
    backend = GcpBackend("my-project", client=client)
    assert backend.self_test() is False


def test_gcp_backend_self_test_false_without_project():
    backend = GcpBackend("", client=_FakeGcpClient())
    assert backend.self_test() is False


# --- open_vault --------------------------------------------------------


def test_open_vault_keychain_does_not_import_google_cloud(monkeypatch):
    monkeypatch.delenv("HEADLESS_SECRETS_BACKEND", raising=False)
    config = load_config(overrides={"secrets_backend": "keychain", "keychain_account": "headless"})
    vault = open_vault(config)
    assert isinstance(vault, KeychainBackend)
    assert "google.cloud.secretmanager" not in sys.modules


def test_open_vault_gcp_returns_gcp_backend():
    config = load_config(overrides={"secrets_backend": "gcp", "gcp_project": "my-project"})
    vault = open_vault(config)
    assert isinstance(vault, GcpBackend)
    assert vault.project == "my-project"
