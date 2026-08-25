# Contracts: Age Vault

**Feature**: 004-age-vault | **Date**: 2026-08-25

Four stable interfaces: the **vault file** itself, the **`AgeBackend` behavior** per failure mode,
the **`scripts/vault.py` CLI**, and the **`check_env.py` vault row and environment variables**.

## 1. The vault file

| Property | Value |
| :--- | :--- |
| Path | `Config.age_file`, resolved from `HEADLESS_AGE_FILE` (absolute or `~`-relative only), default `~/.headless/profile.age` |
| Format | `age -e -p -a` ASCII-armored ciphertext; decrypts to one JSON object (`VaultDocument`, data-model.md) |
| Permissions | `0600` after every write; a documented no-op on Windows |
| Written by | `scripts/vault.py` only (`init`, `set`, `unset`) |
| Read by | `AgeBackend.get_secret` (once per process); `scripts/vault.py`'s `set`, `unset`, `list` |
| Never written by | `AgeBackend` (`put_secret`/`delete_secret` raise) |
| Never read for content by | `scripts/vault.py path` (path resolution only, no `age` invocation) |

**What a reader may assume**: a file that exists and decrypts under the correct passphrase parses
as a `dict[str, str]`. A missing file is the expected shape of a machine that has not run
`vault.py init` yet, not a fault.

**What a reader may never assume**: that the file's content, once decrypted, is safe to print,
log, or place in any preview artifact. Every value in it is exactly the kind of typed value
`CLAUDE.md`'s Secrets section already governs.

## 2. `AgeBackend` behavior

### `get_secret(name)`

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| First call this process, vault file exists, correct passphrase entered | Runs the injected runner (or `age -d <file>`) once, captures stdout in memory, parses JSON, caches it. | The prompt appears on the terminal exactly once. Returns `document[name]` if present. |
| First call this process, vault file exists, wrong passphrase entered | Runner exits nonzero. | Raises a value-free error: `age exited <code>: wrong passphrase or corrupted vault`. Never `age`'s own stderr text. Nothing cached; the next call re-attempts the decrypt (still counts as the process's "first call" state, since nothing succeeded). |
| First call this process, vault file does not exist | No runner call is made. | Raises a config-style error naming only the resolved path (for example: `vault file not found: /Users/x/.headless/profile.age (run: python scripts/vault.py init)`). |
| Any call, `name` absent from the cached document | No runner call (already cached, or this is the same failed-decrypt case above). | Raises the existing `SecretMissing(name)`, unchanged. |
| Second or later call this process, any `name` present in the cached document | No runner call at all. | Returns the cached value directly; no prompt. |

### `put_secret(name, value)` / `delete_secret(name)`

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| Any call, in any state | No runner call, no vault file touched. | Raises immediately: `RuntimeError("AgeBackend does not support writes; use scripts/vault.py")` (or equivalent), pointing at the CLI. |

### `self_test()`

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| `age` resolves on `PATH` and the vault file exists | No decrypt attempted. | Returns `True`. Zero runner calls of any kind. |
| `age` missing from `PATH` | No decrypt attempted. | Returns `False`. |
| Vault file missing | No decrypt attempted. | Returns `False`. |

`self_test()` never prompts, under any input, in any state (spec FR-014, SC-005).

## 3. `scripts/vault.py` CLI contract

No flag or environment variable can suppress a required prompt; nothing here overlaps with an
existing errand's argparse surface, since `vault.py` is a maintenance script (`PATTERNS.md`'s
Automation-First CLI pattern), not an `Errand` subclass.

| Subcommand | Precondition checked | Prompts | On success | On failure |
| :--- | :--- | :--- | :--- | :--- |
| `init` | Vault file must NOT already exist | 2 (`age -e -p`'s own enter/confirm) | Creates an empty (`{}`) vault at `0600`; prints the resolved path; exit `0` | File already exists: prints a refusal naming the path; exit `1`; no `age` invocation at all |
| `set NAME` | Vault file must exist | 2 (1 decrypt + `age -e -p`'s enter/confirm) | Vault re-encrypted with `NAME` set to the value read via hidden `getpass`; exit `0`; prints nothing about the value | Vault missing, wrong passphrase, or `age` unreachable: value-free error to stderr; exit `1` |
| `unset NAME` | Vault file must exist | 2 (1 decrypt + `age -e -p`'s enter/confirm) | Vault re-encrypted with `NAME` removed (idempotent: succeeds whether or not `NAME` was present); exit `0` | Same failure shape as `set` |
| `list` | Vault file must exist | 1 (decrypt only) | Prints every item name, one per line, sorted, nothing else; empty vault prints zero lines; exit `0` | Same failure shape as `set`, minus the re-encrypt possibility |
| `path` | None | 0 | Prints the resolved vault file path; exit `0` | Never fails (pure path resolution; does not require the file to exist) |

**Value never on `argv`**: `set NAME`'s value is read via `getpass.getpass()` to a Python string
held only in memory for the duration of the mutate-and-re-encrypt sequence, then piped to `age`'s
`stdin` as part of the whole document's JSON bytes - never passed as a command-line argument to
any subprocess this script starts (spec SC-008). This is the one place this feature's own design
differs from `KeychainBackend.put_secret`'s accepted, documented residual (`security`'s `-w`
argv exposure, `PATTERNS.md`'s FIX-FIRST 13 entry) - `vault.py` has no equivalent residual because
`age` offers a `stdin` path the `security` CLI does not.

**Exit code convention**: `0` success, `1` a vault-level refusal or failure (missing file when one
was required, an existing file when `init` was asked to create one, a wrong passphrase, `age`
unreachable), `2` a usage error (argparse's own handling of a missing `NAME` argument or an
unknown flag).

## 4. `check_env.py`'s vault row (age backend)

| Condition | Status | Hint |
| :--- | :--- | :--- |
| `age` resolves on `PATH` and the vault file exists | PASS | (none) |
| `age` not found on `PATH` | FAIL | `brew install age` (macOS) - the row's hint text names the install command for whichever platform this check runs on, per README's First-time setup section |
| Vault file does not exist | FAIL | `python scripts/vault.py init` |

No row state ever attempts a decrypt (spec FR-014, D7). This row's contract for the `keychain` and
`gcp` backends is unchanged from before this feature: only the `age` backend's row logic is new.

## 5. Environment variables

| Variable | Before this feature | After this feature |
| :--- | :--- | :--- |
| `HEADLESS_SECRETS_BACKEND` | default `keychain`; valid values `keychain`, `gcp` | default `age`; valid values `keychain`, `gcp`, `age` |
| `HEADLESS_AGE_FILE` | did not exist | new; default `~/.headless/profile.age`; must resolve absolute after `~`-expansion or `ConfigError` is raised (mirrors `HEADLESS_PREVIEW_DIR`'s existing relative-path refusal, not `HEADLESS_PROFILE_DIR`'s more permissive handling) |

No other environment variable changes. `HEADLESS_KEYCHAIN_ACCOUNT` and `HEADLESS_GCP_PROJECT`
keep their existing meaning and defaults for anyone who still selects those backends explicitly.
