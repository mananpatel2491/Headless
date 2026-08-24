"""The secrets vault seam.

One interface, two backends: `KeychainBackend` (macOS `security` CLI, default)
and `GcpBackend` (Google Cloud Secret Manager, selectable). `google.cloud` is
imported lazily inside `GcpBackend`, only when a client is actually needed and
none was injected, so the base install never requires
`google-cloud-secret-manager` (D3). Values are never echoed to Headless's own
stdout/stderr/logs: `put_secret` passes a value via `-w <value>` to `security`
and never prints subprocess output containing it, and a failed write raises
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
"""

from __future__ import annotations

import subprocess
from typing import Protocol

from headless.config import Config

SELFTEST_ITEM = "headless-selftest"


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


def open_vault(config: Config) -> VaultBackend:
    if config.secrets_backend == "keychain":
        return KeychainBackend(config.keychain_account)
    if config.secrets_backend == "gcp":
        return GcpBackend(config.gcp_project)
    raise ValueError(f"unknown secrets backend: {config.secrets_backend!r}")
