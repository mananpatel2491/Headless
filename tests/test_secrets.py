"""Unit tests for headless/secrets.py: FakeVault, the exact `security` argv
KeychainBackend builds (subprocess patched, no real Keychain touched), the
GcpBackend NotFound -> SecretMissing mapping with a fake client, AgeBackend's
decrypt-once-and-cache/failure-mode/write-refusal/self_test contract with an
injectable fake runner (spec 004-age-vault; zero real `age` invocations,
NFR-002), and open_vault backend selection with proof that the keychain path
never imports google.cloud (D3).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from headless.config import ConfigError, load_config
from headless.gates import GateRefused
from headless.profile import ProfileRegistry
from headless.secrets import AgeBackend, GcpBackend, KeychainBackend, SecretMissing, open_vault

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
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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


# --- AgeBackend (spec 004-age-vault; fake runner, zero real `age` calls) ---

AGE_FIXTURE_DOCUMENT = {
    "profile": json.dumps({"identity": {"name": "Test Testerson"}}),
    "other-item": "fixture-value-1",
}


def _age_fake_runner(calls, document=None, returncode=0, stdout=None, stderr=""):
    """A fake runner recording every argv it was called with, returning a
    successful (or overridden) age -d result. Never touches the real `age`
    binary (NFR-002)."""
    document = AGE_FIXTURE_DOCUMENT if document is None else document

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        payload = stdout if stdout is not None else json.dumps(document).encode("utf-8")
        return _FakeCompleted(returncode=returncode, stdout=payload, stderr=stderr)

    return fake_runner


def test_age_backend_decrypts_once_and_caches(tmp_path):
    # T004 (SC-002): first get_secret call decrypts; a second call for a
    # different name is served from the cache with no additional runner call.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    calls = []
    backend = AgeBackend(vault_file, runner=_age_fake_runner(calls))

    value = backend.get_secret("other-item")
    assert value == AGE_FIXTURE_DOCUMENT["other-item"]
    assert calls == [["age", "-d", str(vault_file)]]

    value2 = backend.get_secret("profile")
    assert value2 == AGE_FIXTURE_DOCUMENT["profile"]
    assert calls == [["age", "-d", str(vault_file)]]  # no additional call


def test_age_backend_missing_vault_file_raises_config_error_zero_runner_calls(tmp_path):
    # T005: vault file missing -> config-style error naming only the path,
    # zero runner calls.
    vault_file = tmp_path / "does-not-exist.age"
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        raise AssertionError("runner must never be called when the vault file is missing")

    backend = AgeBackend(vault_file, runner=fake_runner)
    with pytest.raises(ConfigError) as exc_info:
        backend.get_secret("anything")
    assert str(vault_file) in str(exc_info.value)
    assert "vault.py init" in str(exc_info.value)
    assert calls == []


def test_age_backend_wrong_passphrase_is_value_free(tmp_path):
    # T005 (SC-007): a nonzero exit raises a value-free error naming only the
    # exit code plus the fixed hint; a distinctive fixture stderr string never
    # appears anywhere in the raised exception's message.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    distinctive_stderr = "fixture-stderr-must-never-leak-Xk9fQ2"
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=1, stdout=b"", stderr=distinctive_stderr)

    backend = AgeBackend(vault_file, runner=fake_runner)
    with pytest.raises(GateRefused) as exc_info:
        backend.get_secret("anything")
    message = str(exc_info.value)
    assert "1" in message
    assert "wrong passphrase, corrupted vault, or no terminal for the passphrase prompt" in message
    assert distinctive_stderr not in message
    assert calls == [["age", "-d", str(vault_file)]]


def test_age_backend_non_utf8_stdout_is_treated_as_corrupted_vault(tmp_path):
    # NIT 14: a decode failure (stdout is not valid UTF-8) must fold into the
    # same value-free GateRefused branch as any other corrupted-vault shape,
    # never an uncaught UnicodeDecodeError and never errors="replace" masking
    # the corruption before parsing.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    non_utf8_bytes = b"\xff\xfe\x00 not valid utf-8 at all"
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0, stdout=non_utf8_bytes)

    backend = AgeBackend(vault_file, runner=fake_runner)
    with pytest.raises(GateRefused) as exc_info:
        backend.get_secret("anything")
    message = str(exc_info.value)
    assert "wrong passphrase, corrupted vault, or no terminal for the passphrase prompt" in message
    assert calls == [["age", "-d", str(vault_file)]]


def test_age_backend_failed_decrypt_caches_nothing_and_retries(tmp_path):
    # Contract row: "wrong passphrase entered -> nothing cached; the next
    # call re-attempts the decrypt." A failed first attempt must not poison
    # the cache - a second get_secret call (e.g. after the Director retypes
    # the correct passphrase) must issue a fresh runner call, not reuse
    # anything from the failed attempt.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    calls = []
    attempt = {"n": 0}

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        attempt["n"] += 1
        if attempt["n"] == 1:
            return _FakeCompleted(returncode=1, stdout=b"")
        return _FakeCompleted(returncode=0, stdout=json.dumps(AGE_FIXTURE_DOCUMENT).encode("utf-8"))

    backend = AgeBackend(vault_file, runner=fake_runner)
    with pytest.raises(GateRefused):
        backend.get_secret("other-item")

    value = backend.get_secret("other-item")
    assert value == AGE_FIXTURE_DOCUMENT["other-item"]
    assert calls == [["age", "-d", str(vault_file)], ["age", "-d", str(vault_file)]]


def test_age_backend_name_absent_raises_secret_missing_unchanged(tmp_path):
    # T005: name absent from a successfully decrypted document -> the
    # existing SecretMissing(name), unchanged.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    backend = AgeBackend(vault_file, runner=_age_fake_runner([]))
    with pytest.raises(SecretMissing) as exc_info:
        backend.get_secret("nope")
    assert exc_info.value.name == "nope"


def test_age_backend_put_secret_raises_and_never_calls_runner(tmp_path):
    # T006: put_secret raises immediately, mentioning scripts/vault.py, zero
    # runner calls.
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0)

    backend = AgeBackend(tmp_path / "vault.age", runner=fake_runner)
    with pytest.raises(RuntimeError) as exc_info:
        backend.put_secret("name", "value")
    assert "scripts/vault.py" in str(exc_info.value)
    assert calls == []


def test_age_backend_delete_secret_raises_and_never_calls_runner(tmp_path):
    # T006: delete_secret raises immediately, mentioning scripts/vault.py,
    # zero runner calls.
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0)

    backend = AgeBackend(tmp_path / "vault.age", runner=fake_runner)
    with pytest.raises(RuntimeError) as exc_info:
        backend.delete_secret("name")
    assert "scripts/vault.py" in str(exc_info.value)
    assert calls == []


def test_age_backend_self_test_true_when_age_and_file_present(tmp_path, monkeypatch):
    # T006 (SC-005): self_test() returns True when PATH lookup and file
    # existence both succeed, with zero decrypt-shaped runner calls.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr("headless.secrets.shutil.which", lambda name: "/opt/homebrew/bin/age")
    backend = AgeBackend(vault_file, runner=fake_runner)
    assert backend.self_test() is True
    assert calls == []


def test_age_backend_self_test_false_when_age_missing(tmp_path, monkeypatch):
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")

    def fake_runner(argv, **kwargs):
        raise AssertionError("self_test must never invoke the runner")

    monkeypatch.setattr("headless.secrets.shutil.which", lambda name: None)
    backend = AgeBackend(vault_file, runner=fake_runner)
    assert backend.self_test() is False


def test_age_backend_self_test_false_when_vault_file_missing(tmp_path, monkeypatch):
    vault_file = tmp_path / "does-not-exist.age"

    def fake_runner(argv, **kwargs):
        raise AssertionError("self_test must never invoke the runner")

    monkeypatch.setattr("headless.secrets.shutil.which", lambda name: "/opt/homebrew/bin/age")
    backend = AgeBackend(vault_file, runner=fake_runner)
    assert backend.self_test() is False


def test_age_backend_feeds_profile_registry(tmp_path):
    # T012: an AgeBackend constructed with a fake runner whose fixture
    # document holds a `profile` key feeds ProfileRegistry.load correctly,
    # proving FR-006's "unchanged consumer contract" end to end.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    backend = AgeBackend(vault_file, runner=_age_fake_runner([]))
    registry = ProfileRegistry.load(backend)
    assert registry.get("identity.name") == "Test Testerson"


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


def test_open_vault_age_returns_age_backend(tmp_path):
    vault_file = tmp_path / "vault.age"
    config = load_config(overrides={"secrets_backend": "age", "age_file": str(vault_file)})
    vault = open_vault(config)
    assert isinstance(vault, AgeBackend)
    assert vault.vault_file == vault_file


def test_open_vault_age_is_the_default(monkeypatch):
    # SC-003 at the open_vault level: HEADLESS_SECRETS_BACKEND unset resolves
    # to the age backend with no environment variable set by hand (FR-002).
    monkeypatch.delenv("HEADLESS_SECRETS_BACKEND", raising=False)
    config = load_config()
    vault = open_vault(config)
    assert isinstance(vault, AgeBackend)
