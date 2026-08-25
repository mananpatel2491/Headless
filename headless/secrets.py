"""The secrets vault seam.

One interface, three backends: `AgeBackend` (a local, passphrase-encrypted
`age` vault - the default, spec 004-age-vault), `KeychainBackend` (macOS
`security` CLI), and `GcpBackend` (Google Cloud Secret Manager, selectable,
its activation plan superseded by the age vault). `google.cloud` is imported
lazily inside `GcpBackend`, only when a client is actually needed and none was
injected, so the base install never requires `google-cloud-secret-manager`
(D3). Values are never echoed to Headless's own stdout/stderr/logs:
`KeychainBackend.put_secret` passes a value via `-w <value>` to `security` and
never prints subprocess output containing it, and a failed write raises
`RuntimeError` naming only the item and the `security` exit code, never the
value.

FIX-FIRST 13 truthfulness note: `security add-generic-password` has no stdin
path for the value; `-w <value>` is the only interface `security` offers, so
the value is a real argv element of the child process for the duration of the
call and is visible to local tools that can read another process's argv
(`ps -ww`, `/proc`-equivalents) on this machine for that brief window. This is
accepted for a single-user Mac Headless already trusts with the Keychain
itself; the `profile` item in particular is meant to be seeded by hand (or by
a future dedicated `profile_put.py`), not written by an unattended errand.
`AgeBackend` has no equivalent residual: `age` reads its passphrase from the
controlling terminal directly, never from anything Python passes it, and
`scripts/vault.py`'s own write path pipes every value through `stdin`, never
`argv` (spec SC-008; see `AgeBackend`'s own docstring below and
specs/004-age-vault/research.md D4/D6).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Protocol

from headless.config import Config, ConfigError
from headless.gates import GateRefused

SELFTEST_ITEM = "headless-selftest"

# The one fixed hint FR-012/NFR-004 allow for a failed decrypt (wrong
# passphrase, or a corrupted/non-age file): never age's own exit code alone,
# never any fragment of its stderr. Shared by AgeBackend.get_secret and
# scripts/vault.py's own DECRYPT step so both callers refuse identically
# (spec Edge Cases: "this applies identically whether the caller is
# AgeBackend.get_secret or scripts/vault.py's own read step").
DECRYPT_FAILURE_HINT = "wrong passphrase, corrupted vault, or no terminal for the passphrase prompt"


class SecretMissing(KeyError):
    """Raised when a named secret (or the `profile` registry item) is not in the vault."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"secret {self.name!r} not found in the vault"


class VaultBackend(Protocol):
    def get_secret(self, name: str) -> str: ...

    def put_secret(self, name: str, value: str) -> None: ...

    def delete_secret(self, name: str) -> None: ...

    def self_test(self) -> bool: ...


class KeychainBackend:
    """macOS Keychain generic-password items, addressed by name under one account."""

    def __init__(self, account: str) -> None:
        self.account = account

    def get_secret(self, name: str) -> str:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", self.account, "-s", name, "-w"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SecretMissing(name)
        return result.stdout.rstrip("\n")

    def put_secret(self, name: str, value: str) -> None:
        try:
            subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-a",
                    self.account,
                    "-s",
                    name,
                    "-w",
                    value,
                    "-U",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            # Never let the CalledProcessError propagate: its `.cmd` holds
            # the argv, including the raw value passed via -w.
            raise RuntimeError(f"keychain write failed for item {name!r} (security exit {exc.returncode})") from None

    def delete_secret(self, name: str) -> None:
        try:
            subprocess.run(
                ["security", "delete-generic-password", "-a", self.account, "-s", name],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"keychain write failed for item {name!r} (security exit {exc.returncode})") from None

    def self_test(self) -> bool:
        self.put_secret(SELFTEST_ITEM, "ok")
        try:
            return self.get_secret(SELFTEST_ITEM) == "ok"
        finally:
            self.delete_secret(SELFTEST_ITEM)


class GcpBackend:
    """Google Cloud Secret Manager backend. Code-ready, activated later (D3).

    `google.cloud.secretmanager` is imported only inside `_get_client`, and
    only when no `client` was injected, so unit tests can pass a fake client
    without the package being installed.
    """

    def __init__(self, project: str, client: object | None = None) -> None:
        self.project = project
        self._client = client

    def _get_client(self):
        if self._client is None:
            from google.cloud import secretmanager  # lazy: optional extra

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def get_secret(self, name: str) -> str:
        client = self._get_client()
        version_name = f"projects/{self.project}/secrets/{name}/versions/latest"
        try:
            response = client.access_secret_version(name=version_name)
        except Exception as exc:
            if type(exc).__name__ == "NotFound":
                raise SecretMissing(name) from exc
            raise
        return response.payload.data.decode("utf-8")

    def put_secret(self, name: str, value: str) -> None:
        client = self._get_client()
        parent = f"projects/{self.project}"
        secret_path = f"{parent}/secrets/{name}"
        try:
            client.get_secret(name=secret_path)
        except Exception as exc:
            if type(exc).__name__ == "NotFound":
                client.create_secret(
                    parent=parent,
                    secret_id=name,
                    secret={"replication": {"automatic": {}}},
                )
            else:
                raise
        client.add_secret_version(parent=secret_path, payload={"data": value.encode("utf-8")})

    def delete_secret(self, name: str) -> None:
        client = self._get_client()
        client.delete_secret(name=f"projects/{self.project}/secrets/{name}")

    def self_test(self) -> bool:
        if not self.project:
            return False
        try:
            client = self._get_client()
            client.list_secrets(request={"parent": f"projects/{self.project}", "page_size": 1})
        except Exception:
            return False
        return True


def _default_age_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, **kwargs)


def decrypt_age_document(vault_file: Path, runner: Callable[..., object]) -> dict[str, str]:
    """The DECRYPT step (data-model.md), shared by `AgeBackend.get_secret` and
    `scripts/vault.py`'s own `set`/`unset`/`list` subcommands so both callers
    refuse identically (spec Edge Cases). Runs `age -d <vault_file>` via
    `runner`, captures its stdout entirely in memory (never written to disk),
    and parses it as a `VaultDocument` - a flat `dict[str, str]`.

    A missing vault file raises before `runner` is ever called (FR-011). A
    nonzero exit, non-UTF-8 or unparseable JSON output, or a decrypted value
    that is not a JSON object of strings (data-model.md's "non-string value
    is a corrupted vault, the same failure class as a decrypt error") all
    raise the same value-free `GateRefused`: `age`'s exit code plus the one
    fixed hint, never any part of its stderr (FR-012, NFR-004). A decode
    failure is folded into this same branch deliberately, never decoded with
    `errors="replace"`: a byte sequence that is not valid UTF-8 IS a
    corrupted vault, not something to paper over before parsing.
    """
    if not vault_file.exists():
        raise ConfigError(f"vault file not found: {vault_file} (run: python scripts/vault.py init)")

    result = runner(["age", "-d", str(vault_file)], capture_output=True)
    if result.returncode != 0:
        raise GateRefused(f"age exited {result.returncode}: {DECRYPT_FAILURE_HINT}")

    stdout = result.stdout
    try:
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8")
        document = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GateRefused(f"age exited {result.returncode}: {DECRYPT_FAILURE_HINT}") from None
    if not isinstance(document, dict) or not all(isinstance(v, str) for v in document.values()):
        raise GateRefused(f"age exited {result.returncode}: {DECRYPT_FAILURE_HINT}")
    return document


class AgeBackend:
    """A local, passphrase-encrypted `age` vault (spec 004-age-vault) - the
    default backend (D1).

    `get_secret` decrypts at most once per instance: the first call runs
    `decrypt_age_document` and caches the resulting mapping for the rest of
    this process's life; every later call, for any name, is served from that
    cache with no further decrypt and no further prompt (FR-007, SC-002,
    data-model.md's `locked` -> `decrypted-cached` transition, which never
    reverts). `age` prompts for the passphrase on the controlling terminal
    directly, never on this process's stdin/stdout, so no code here ever
    sees, holds, or could log the passphrase's characters (FR-008, NFR-001).

    The constructor accepts an optional injectable `runner` callable
    (default: a thin wrapper around `subprocess.run`) so every branch is
    unit-testable without invoking the real `age` binary and without ever
    prompting for a passphrase (FR-009, NFR-002).

    `put_secret`/`delete_secret` always raise: `scripts/vault.py` is the only
    place the vault is ever written, so an errand can never trigger a
    surprise re-encrypt prompt chain (FR-013). `self_test()` never decrypts
    or prompts; it only checks that `age` resolves on PATH and that the
    vault file exists (FR-014, SC-005), so `scripts/check_env.py` stays a
    prompt-free, few-second self-test.
    """

    def __init__(self, vault_file: Path, runner: Callable[..., object] | None = None) -> None:
        self.vault_file = Path(vault_file)
        self._runner = runner or _default_age_runner
        self._cache: dict[str, str] | None = None

    def get_secret(self, name: str) -> str:
        if self._cache is None:
            self._cache = decrypt_age_document(self.vault_file, self._runner)
        if name not in self._cache:
            raise SecretMissing(name)
        return self._cache[name]

    def put_secret(self, name: str, value: str) -> None:
        raise RuntimeError("AgeBackend does not support writes; use scripts/vault.py")

    def delete_secret(self, name: str) -> None:
        raise RuntimeError("AgeBackend does not support writes; use scripts/vault.py")

    def self_test(self) -> bool:
        return shutil.which("age") is not None and self.vault_file.exists()


def open_vault(config: Config) -> VaultBackend:
    if config.secrets_backend == "keychain":
        return KeychainBackend(config.keychain_account)
    if config.secrets_backend == "gcp":
        return GcpBackend(config.gcp_project)
    if config.secrets_backend == "age":
        return AgeBackend(config.age_file)
    raise ValueError(f"unknown secrets backend: {config.secrets_backend!r}")
