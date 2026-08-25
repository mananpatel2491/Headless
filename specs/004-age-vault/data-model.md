# Data Model: Age Vault

**Feature**: 004-age-vault | **Date**: 2026-08-25

No database. The only persisted artifact is the vault file this feature introduces (default
`~/.headless/profile.age`); everything else here is either in-memory for the lifetime of one
process (`AgeBackend`'s cache) or a description of `scripts/vault.py`'s own operation sequence.
The vault file's content shape and invariants, `AgeBackend`'s state machine, and the CLI's
operation lifecycle are the entire data model.

## VaultDocument

The complete plaintext content of the vault, once decrypted: a JSON object, nothing else. There
is no wrapping array, no version field, no metadata - the file's whole decrypted content is the
object, matching the shape `get_secret(name)` already promises its callers.

| Field | Type | Rules |
| :--- | :--- | :--- |
| (the decrypted root value) | `dict[str, str]` | every key is an item name; every value is a plain string. The object MAY be empty (`{}`, the shape `vault.py init` creates). No value MAY be a nested object, an array, a number, or any other non-string JSON type - `AgeBackend` treats a non-string value as a corrupted vault, the same failure class as a decrypt error. |

**Invariant - `profile` is a registry, not a special case**: the item named `"profile"` holds a
JSON string that `ProfileRegistry.load` parses as its own nested document (identity, address, and
similar fields, dotted-path addressable). `VaultDocument` itself does not know or care about this
- it is a string like any other item's value. Every other item name is one individual secret
string with no further structure implied.

**Invariant - no password, no card**: no key in this document may hold a password or a payment
card value, at any time (spec FR-023). This is a policy invariant, not a structurally enforced
one - nothing in `AgeBackend` inspects a value's shape to detect one - the same way
`headless/fields.py`'s "registry is the only writable source" invariant is enforced by the
absence of any other code path to type a value, not by inspecting what gets typed.

**Invariant - whole-document replace**: every `scripts/vault.py` write (`init`, `set`, `unset`)
replaces the vault file's entire encrypted content with a freshly re-encrypted copy of the
in-memory document after the one mutation that operation makes. There is no partial write and no
merge step at the file level - the mutation happens to the in-memory dict, and the whole dict is
re-encrypted as one unit, the same shape v0.0.3's `SessionCookieState` uses for its own
whole-file-replace export.

## VaultFile (the on-disk artifact)

| Property | Value |
| :--- | :--- |
| Path | `Config.age_file` (`headless/config.py`), resolved from `HEADLESS_AGE_FILE`, default `~/.headless/profile.age` |
| Format | `age`'s own ASCII-armored ciphertext (a text file beginning `-----BEGIN AGE ENCRYPTED FILE-----`), produced by `age -e -p -a`; decrypts, via `age -d`, to the `VaultDocument` JSON above |
| Permissions | `0600` on every write (`init`, `set`, `unset`), enforced the same way v0.0.3's `session-cookies.json` enforces its own mode; a documented no-op on Windows |
| Written by | `scripts/vault.py` only (`init`, `set`, `unset`) |
| Read by | `AgeBackend.get_secret` (once per process, cached); `scripts/vault.py`'s `set`, `unset`, and `list` subcommands (each its own decrypt); never by `path`, which only resolves and prints the path |
| Never written by | `AgeBackend` - `put_secret`/`delete_secret` raise instead (FR-013) |
| Never contains, at rest or in memory beyond the moment of use | the passphrase itself (D4); a plaintext copy on disk at any point (D6) |

**What a reader may assume**: if the file exists and `age -d` succeeds against it, the result
parses as a `VaultDocument`. A reader MUST NOT assume the file exists at all (a fresh clone has
none until `vault.py init` runs) and MUST NOT assume a missing file means anything went wrong -
it is the expected shape of an unset-up machine (spec Edge Cases).

**What a reader may never assume**: that the file's content, or anything derived from decrypting
it, is safe to print, log, or include in any output. Every value inside it is exactly the kind of
typed value `CLAUDE.md`'s Secrets section already governs; nothing about this file's mechanism
changes that classification.

## AgeBackend: states

`AgeBackend` has exactly two states across its lifetime within one process, transitioning exactly
once:

```text
locked (constructed, no get_secret call has happened yet)
  │
  │  first get_secret(name) call:
  │    run <runner>("age", "-d", str(vault_file))     # D4
  │    on success: parse stdout as JSON -> VaultDocument, cache it
  │    on missing file: raise a config-style error naming only the path
  │    on nonzero exit: raise a value-free error naming only the exit code
  │                      plus the fixed hint "wrong passphrase or corrupted vault"
  ▼
decrypted-cached (the VaultDocument is held in memory for the rest of this process)
  │
  │  every later get_secret(name) call, for any name:
  │    read from the cached VaultDocument directly - no runner call, no prompt
  │    name present  -> return its string value
  │    name absent   -> raise SecretMissing(name)     # unchanged contract
  ▼
decrypted-cached (unchanged; this state never reverts to locked within one process)
```

`put_secret`/`delete_secret` are not part of this state machine at all: calling either, in either
state, raises immediately, pointing at `scripts/vault.py`, and has no effect on `locked` versus
`decrypted-cached`.

`self_test()` is also independent of this state machine: it checks `PATH` and file existence only
and never triggers the `locked -> decrypted-cached` transition (D7, FR-014).

**Ordering guarantee**: within one process, no `get_secret` call can ever observe a partially
decrypted or partially cached document - the transition is one atomic assignment in Python
(`self._cache = document`) immediately after a successful parse, with no `get_secret` call able to
interleave with it (this codebase has no concurrency inside one process for this seam).

## `scripts/vault.py`: operation lifecycle

Every subcommand that touches the vault's content follows the same three-step shape; `path` skips
all three, and `init` skips the first (there is nothing to decrypt yet):

```text
DECRYPT (init: skipped; set / unset / list):
  run age -d <vault_file>, capturing stdout entirely in memory
  parse as VaultDocument
  on any failure: print the value-free error, exit non-zero, stop
    (no MUTATE or RE-ENCRYPT step runs)

MUTATE (in-memory only; init starts from {} instead of a decrypted document):
  set NAME   -> read the new value via getpass (hidden, never argv); document[NAME] = value
  unset NAME -> document.pop(NAME, None)   # succeeds whether or not NAME was present
  list       -> no mutation; print sorted(document.keys()), one per line, then stop
               (no RE-ENCRYPT step runs - list is read-only)
  init       -> document = {}

RE-ENCRYPT (init / set / unset only):
  json_bytes = json.dumps(document).encode()
  run age -e -p -a -o <tmp_path> with json_bytes piped to its stdin   # D6
  chmod 0600 <tmp_path>                                    # no-op on Windows
  os.replace(<tmp_path>, <vault_file>)
```

**Failure isolation**: a failed DECRYPT step never reaches MUTATE or RE-ENCRYPT - the vault file
on disk is left exactly as it was. A failed RE-ENCRYPT (the `age -e` call itself fails, or the
write to `tmp_path` fails) never touches `<vault_file>` at all, because `os.replace` is the last
step and only runs after a successful write; the previous vault file survives unchanged. This
mirrors the failure-isolation guarantee `specs/003-login-persistence/data-model.md` already
states for `_import_session_cookies`/`_export_session_cookies`: a failure on one side of an
atomic operation never corrupts or partially overwrites what was there before.

**Prompt accounting**: `init` prompts twice (the RE-ENCRYPT step's own enter/confirm dialog, since
there is no DECRYPT step). `set` and `unset` each prompt twice (once for DECRYPT, once for
RE-ENCRYPT's enter/confirm). `list` prompts once (DECRYPT only). `path` never prompts (neither
step runs). No prompt count is ever reduced by caching across separate `vault.py` invocations
(FR-021) - each process run is independent, matching `AgeBackend`'s own per-process-only cache.
