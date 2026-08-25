#!/usr/bin/env python3
"""vault: the only place the local age-encrypted vault is ever written.

Background (spec 004-age-vault): the vault holds everything the macOS
Keychain held before, plus everything GCP Secret Manager was meant to hold -
one `age`-encrypted JSON object, mapping item names to string values,
decrypted only when the Director types the vault's passphrase on this
process's controlling terminal (research.md D4-D6). `headless/secrets.py`'s
`AgeBackend` is read-only by design (`put_secret`/`delete_secret` raise); this
script is the only place a write happens, so an errand can never trigger a
surprise re-encrypt prompt chain (FR-013).

Site: none. This maintenance script never opens a browser window.
Reads: the vault file named by `Config.age_file` (default
`~/.headless/profile.age`).
Writes: the same file, only via `init` (refuses if it already exists), `set
NAME`, and `unset NAME` - every write re-encrypts the whole document
atomically (temp file in the vault's own directory, then `os.replace`, mode
`0600` where the platform supports it).
Secrets / profile fields: whatever the Director chooses to `set`. Per
CLAUDE.md's Secrets section, never a password or a payment card value
(FR-023) - a login persists through the v0.0.3 session-cookie mechanism
instead, and any payment action stays human-only.
Handoff: none; this is not a browser errand.

Every subcommand that reads or writes the vault triggers its own passphrase
prompt; nothing is cached across invocations, or across processes (FR-021).
`set NAME`'s value is read via hidden `getpass` input, never `argv` and never
an environment variable (FR-017, SC-008) - it reaches `age` only through
piped stdin bytes built in memory.

`get NAME` (v0.0.4.1) prints item NAME's raw value to stdout - the one
deliberate, documented exception to the never-print-values rule: a
Director-invoked read of his own vault, on his own terminal, behind the
passphrase prompt, for the fetch -> edit in an editor -> `set` round trip.
The rule holds everywhere non-interactive: no log, artifact, or error
message ever carries a value, and no errand code path calls `get`.

Usage:
    python scripts/vault.py init
    python scripts/vault.py get NAME
    python scripts/vault.py set NAME
    python scripts/vault.py unset NAME
    python scripts/vault.py list
    python scripts/vault.py path

Exit codes: 0 success, 1 a vault-level refusal (missing file, an existing
file when init was asked to create one, a wrong passphrase, age
unreachable), 2 a usage error (argparse's own handling).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

# Same convention as the Director's Atlassian toolkit: no packaging step for a
# personal tool, just insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless.config import Config, ConfigError, load_config
from headless.gates import GateRefused
from headless.secrets import decrypt_age_document

# A value-free hint for a failed RE-ENCRYPT (age -e) call, distinct from
# DECRYPT_FAILURE_HINT ("wrong passphrase, corrupted vault, or no terminal for the passphrase prompt", which is
# specifically about a failed *decrypt*, FR-012). Never echoes age's stderr
# (NFR-004).
ENCRYPT_FAILURE_HINT = "age encrypt failed"


def _default_runner(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(argv, **kwargs)


def _encrypt_document(document: dict[str, str], vault_file: Path, runner: Callable[..., object]) -> None:
    """The RE-ENCRYPT step (data-model.md), used by `init`/`set`/`unset`.

    The whole document's JSON bytes are piped to `age -e -p -a` via `stdin`
    (never a temp plaintext file, D6); the resulting ciphertext is captured
    from `stdout` and written to a temp file in the vault's own directory,
    chmod 0600 (a documented no-op on Windows, FR-022), then atomically
    replaced onto the vault path. The write-through-replace sequence is
    wrapped so a failure anywhere between the temp write and the atomic
    replace always unlinks the temp file (best-effort) before propagating -
    mirroring the mechanical shape `headless/session.py`'s
    `_export_session_cookies` established for `session-cookies.json` in
    v0.0.3 (that cleanup exists because the v0.0.3 verifier demanded it).
    Unlike that fail-soft cookie-file path, a vault write failure here is
    never swallowed: the vault is the thing of record, not a best-effort
    cache, so the exception is re-raised for the caller to see.
    """
    json_bytes = json.dumps(document).encode("utf-8")
    result = runner(["age", "-e", "-p", "-a"], input=json_bytes, capture_output=True)
    if result.returncode != 0:
        raise GateRefused(f"age exited {result.returncode}: {ENCRYPT_FAILURE_HINT}")

    ciphertext = result.stdout
    if isinstance(ciphertext, str):
        ciphertext = ciphertext.encode("utf-8")

    vault_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = vault_file.parent / f"{vault_file.name}.tmp"
    try:
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(ciphertext)
        try:
            os.chmod(str(tmp_path), 0o600)
        except OSError:
            pass  # Windows: no-op (FR-022), never raises there.
        os.replace(str(tmp_path), str(vault_file))
    except Exception:
        # Best-effort cleanup: never leave a stray ciphertext temp file
        # behind. This cleanup itself can never raise (a second failure here
        # still must not mask the original one being re-raised below).
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def cmd_init(config: Config, runner: Callable[..., object]) -> int:
    if config.age_file.exists():
        print(f"REFUSED: vault file already exists: {config.age_file}")
        return 1
    try:
        _encrypt_document({}, config.age_file, runner)
    except GateRefused as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(str(config.age_file))
    return 0


def cmd_set(name: str, config: Config, runner: Callable[..., object]) -> int:
    try:
        document = decrypt_age_document(config.age_file, runner)
    except (ConfigError, GateRefused) as exc:
        print(f"REFUSED: {exc}")
        return 1
    value = getpass.getpass(f"Value for {name!r} (hidden, never echoed): ")
    document[name] = value
    try:
        _encrypt_document(document, config.age_file, runner)
    except GateRefused as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"set: {name}")
    return 0


def cmd_get(name: str, config: Config, runner: Callable[..., object]) -> int:
    try:
        document = decrypt_age_document(config.age_file, runner)
    except (ConfigError, GateRefused) as exc:
        print(f"REFUSED: {exc}")
        return 1
    if name not in document:
        print(f"REFUSED: item {name!r} not in the vault")
        return 1
    print(document[name])
    return 0


def cmd_unset(name: str, config: Config, runner: Callable[..., object]) -> int:
    try:
        document = decrypt_age_document(config.age_file, runner)
    except (ConfigError, GateRefused) as exc:
        print(f"REFUSED: {exc}")
        return 1
    document.pop(name, None)
    try:
        _encrypt_document(document, config.age_file, runner)
    except GateRefused as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"unset: {name}")
    return 0


def cmd_list(config: Config, runner: Callable[..., object]) -> int:
    try:
        document = decrypt_age_document(config.age_file, runner)
    except (ConfigError, GateRefused) as exc:
        print(f"REFUSED: {exc}")
        return 1
    for name in sorted(document):
        print(name)
    return 0


def cmd_path(config: Config) -> int:
    print(str(config.age_file))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the local age-encrypted vault. The only place it is ever written."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create a new, empty vault. Refuses if one already exists.")

    set_parser = subparsers.add_parser("set", help="Set NAME's value via a hidden prompt (never argv).")
    set_parser.add_argument("name")

    get_parser = subparsers.add_parser(
        "get",
        help="Print NAME's raw value to stdout (the documented Director-terminal exception).",
    )
    get_parser.add_argument("name")

    unset_parser = subparsers.add_parser("unset", help="Remove NAME. Succeeds whether or not it was present.")
    unset_parser.add_argument("name")

    subparsers.add_parser("list", help="Print every item name, one per line. Never prints a value.")

    subparsers.add_parser("path", help="Print the resolved vault file path. Never touches the file's contents.")

    return parser


def main(argv: list[str] | None = None, *, runner: Callable[..., object] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    active_runner = runner or _default_runner

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"REFUSED: {exc}")
        return 1

    if args.command == "init":
        return cmd_init(config, active_runner)
    if args.command == "set":
        return cmd_set(args.name, config, active_runner)
    if args.command == "get":
        return cmd_get(args.name, config, active_runner)
    if args.command == "unset":
        return cmd_unset(args.name, config, active_runner)
    if args.command == "list":
        return cmd_list(config, active_runner)
    if args.command == "path":
        return cmd_path(config)
    raise AssertionError(f"unhandled subcommand: {args.command!r}")  # argparse's `required=True` prevents this


if __name__ == "__main__":
    raise SystemExit(main())
