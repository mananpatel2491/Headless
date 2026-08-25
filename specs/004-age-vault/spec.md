# Feature Specification: Age Vault

**Feature Branch**: `v0.0.4` (spec directory `004-age-vault`)

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "Revise the secrets strategy: drop GCP Secret Manager plus PAM
approval (that plan is superseded) in favor of a local, open-source vault encrypted with a
password the user must type by hand - there is no option to save it - available locally, and
holding all of the Director's sensitive information. Passwords and payment card data are never
stored in any backend: a login persists through the v0.0.3 session-cookie mechanism, and paying
stays a human-only action per the constitution. First-time setup must be encoded in the repo
itself, so anyone cloning it can set up the vault on their own machine, macOS or Windows,
without asking a person how."

## Why

The v0.0.1 secrets plan named GCP Secret Manager as the eventual backend. Building it out would
have meant a second Google account (Google forbids a person approving their own Privileged
Access Manager grant, so a single-Director tool would need someone else to hold the approver
role), a standing cloud dependency, and a monthly cost for a tool that has exactly one user. The
Director reviewed that plan and replaced it: a local, passphrase-encrypted file, using the
open-source `age` tool, holding everything the macOS Keychain currently holds and everything
GCP Secret Manager was meant to hold, with one property neither of those backends can offer as
naturally - the passphrase itself never has a chance to enter this codebase's own memory, because
`age` reads it from the terminal directly, not from anything Python passes it. Every time an
errand needs a secret, the Director has to be at the keyboard to type that passphrase in. That is
the approval gate GCP's PAM was meant to provide, built instead from a property of the encryption
tool itself, with no cloud account, no second approver, and no ongoing cost.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The vault holds everything in one encrypted file (Priority: P1)

All of the Director's sensitive profile data - the same class of value the Keychain held before,
plus anything GCP Secret Manager was ever going to hold - lives in one local file, encrypted with
a passphrase only the Director knows. An errand asking for a secret gets it back exactly as it
does today; nothing about the `get_secret(name)` contract changes for a caller.

**Why this priority**: this is the feature. Without a working vault, there is no local backend to
default to, and the whole point of dropping the GCP plan falls through.

**Independent Test**: run `python scripts/vault.py init`, set a `profile` item with a small
synthetic registry, then call `AgeBackend.get_secret("profile")` from a script and confirm it
returns the JSON string unchanged.

**Acceptance Scenarios**:

1. **Given** a vault created with `vault.py init` and a `profile` item set with a JSON registry,
   **When** an errand's field plan resolves a `secret:profile` or `registry:...` source, **Then**
   the vault is decrypted once and the returned value matches what was stored, byte for byte.
2. **Given** a vault holding several named items, **When** `get_secret` is called with a name not
   present in the decrypted mapping, **Then** the existing `SecretMissing` is raised, unchanged
   from today's contract.
3. **Given** `HEADLESS_SECRETS_BACKEND` is left unset, **When** any script loads its
   configuration, **Then** the resolved backend is `age`, with no environment variable set by
   hand.
4. **Given** `HEADLESS_AGE_FILE` is set to a bare relative path, **When** configuration loads,
   **Then** it is refused with a `ConfigError`, the same way an out-of-bounds
   `HEADLESS_PREVIEW_DIR` is refused today.
5. **Given** a process that has already called `get_secret` once, **When** it calls `get_secret`
   again for a different name later in the same run, **Then** no second decrypt happens; the
   second call is served from the first call's in-memory cache.

---

### User Story 2 - Nothing decrypts without the Director typing the passphrase (Priority: P1)

Every time a script needs to reach into the vault, the Director has to type the vault's
passphrase into that specific run, at that specific terminal. There is no saved passphrase, no
cached unlock, and no code path that could see or record what was typed. This is the approval
gate: no human at the keyboard, no secret.

**Why this priority**: this is the property that makes the local vault a legitimate replacement
for GCP's PAM approval step, not just a cheaper storage location. Ranked with User Story 1, not
below it - a vault nobody has to unlock by hand is a vault with no gate at all.

**Independent Test**: run an errand whose field plan touches the registry, confirm the terminal
shows `age`'s own "Enter passphrase" prompt, and confirm no Python code anywhere in the call path
ever holds the typed characters.

**Acceptance Scenarios**:

1. **Given** an errand with any secret- or registry-backed field in its plan, **When** it runs in
   preview, check, or apply mode, **Then** the passphrase prompt appears exactly once on that
   run's terminal, because `errand.py` resolves every plan source before any browser window
   opens, in every mode.
2. **Given** the same errand run with no controlling terminal available (piped output,
   backgrounded, or run from a context with no `/dev/tty`), **When** `age` tries to prompt,
   **Then** the run refuses with a value-free error rather than hanging or silently succeeding.
3. **Given** `probe.py`, whose field plan is empty, **When** it runs in any mode, **Then** no
   decrypt happens and no passphrase prompt appears at all.
4. **Given** the Director types the wrong passphrase, **When** `age` exits with a nonzero status,
   **Then** the run refuses with an error naming only the exit code and a fixed hint, never
   `age`'s raw stderr and never any byte of the vault's content.
5. **Given** `scripts/check_env.py`'s vault row, **When** it runs, **Then** it checks only that
   `age` is reachable on `PATH` and that the vault file exists - it never decrypts and never
   prompts, so `check_env` stays a prompt-free, few-second self-test exactly as it is today.

---

### User Story 3 - First-time setup works from a fresh clone, macOS or Windows (Priority: P2)

Someone who has never run Headless before can clone the repository, follow the README from the
top, and end up with a working vault - without asking anyone how, and without needing to reverse
engineer anything from this feature's design documents.

**Why this priority**: a vault nobody can set up on their own is a vault only the machine that
built it can use. Ranked P2, not P1, because the vault and the gate (User Stories 1 and 2) are
the substance of the feature; this story is about making sure the substance is reachable, which
matters less in the moment this feature ships (the Director's own machine already has an `age`
install) and more the next time this repository is cloned somewhere new.

**Independent Test**: on a machine with nothing Headless-specific installed, follow only the
README's "First-time setup" section, in order, and confirm `python scripts/check_env.py` reports
5/5 PASS at the end with no other guidance consulted.

**Acceptance Scenarios**:

1. **Given** a fresh clone on macOS with nothing installed, **When** the Director follows the
   README's First-time setup section top to bottom, **Then** `age`, the Python environment, the
   commit-safety git hook, and the vault (`init` plus a seeded `profile` item) are all in place,
   and `check_env.py` reports 5/5 PASS, its vault row naming the `age` backend.
2. **Given** the same fresh-clone scenario on Windows, **When** the Director follows the
   Windows-specific commands in the same README section, **Then** the same end state is reached,
   with the section noting that the Keychain backend is macOS-only and `age` is the cross-platform
   default.
3. **Given** a `profile` item already seeded, **When** the Director runs `vault.py list`, **Then**
   only the item's name is printed - never the registry JSON or any value inside it.
4. **Given** a vault file that already exists, **When** `vault.py init` is run again against it,
   **Then** it refuses immediately, before ever invoking `age` or prompting for a passphrase, and
   leaves the existing file untouched.

---

### Edge Cases

- The Director types the wrong passphrase at decrypt: the run refuses with the fixed hint
  ("wrong passphrase, corrupted vault, or no terminal for the passphrase prompt"), no partial
  data is exposed, and this applies identically whether the caller is `AgeBackend.get_secret`
  or `scripts/vault.py`'s own read step.
- The vault file does not exist yet when `get_secret` is called: a config-style error names only
  the resolved path, with a hint to run `vault.py init`; never a stack trace, never vault content
  (there is none to leak).
- The `age` binary is missing from `PATH`: `AgeBackend.self_test()` and `check_env.py`'s vault row
  both report this cleanly with an install hint, without ever attempting a decrypt.
- An errand runs in a context with no controlling terminal (CI, a background job, output fully
  piped): `age` cannot prompt and the decrypt fails; this is an accepted limit, not a defect - any
  secret- or registry-touching run needs a human at an interactive terminal, by design (this is
  the gate, not a bug in it).
- `vault.py list` against a freshly initialized, still-empty vault: prints zero lines, never an
  error.
- Two processes touch the vault at close to the same moment (an errand's read-only decrypt
  alongside a `vault.py set` write): each independently prompts and decrypts on its own; the
  write path's atomic replace means whichever write finishes last simply wins, the same
  last-write-wins semantics the v0.0.3 session-cookie file already accepts for its own writes.
- `HEADLESS_AGE_FILE` is pointed at a path inside the repository: `.gitignore`'s `*.age` entry
  keeps it out of version control as a second line of defense, the same belt-and-braces pattern
  v0.0.3 used for `session-cookies.json`.
- A stored item's value is itself an empty string: `get_secret` returns the empty string, since an
  empty value that was deliberately set is not the same thing as a name that was never set
  (`SecretMissing` is reserved for the latter).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST add `"age"` as a valid value of `HEADLESS_SECRETS_BACKEND`,
  alongside the existing `"keychain"` and `"gcp"` values.
- **FR-002**: The system MUST resolve `HEADLESS_SECRETS_BACKEND` to `"age"` when the variable is
  unset, changing today's default (`"keychain"`).
- **FR-003**: The existing `KeychainBackend` and `GcpBackend` code and behavior MUST NOT be
  removed or altered; both remain selectable via `HEADLESS_SECRETS_BACKEND`.
- **FR-004**: The vault file's path MUST resolve from `HEADLESS_AGE_FILE` when set, defaulting to
  `~/.headless/profile.age`. After `~`-expansion, the resolved path MUST be absolute; a value
  that is still relative after expansion MUST raise `ConfigError`, the same refusal
  `HEADLESS_PREVIEW_DIR` already applies to an out-of-bounds relative override.
- **FR-005**: `.gitignore` MUST exclude every `*.age` file repository-wide, as a second line of
  defense alongside the vault living outside the repository by default.
- **FR-006**: The vault file MUST hold exactly one `age`-encrypted JSON object mapping each item
  name to a single string value. `get_secret("profile")` MUST keep returning the registry JSON
  string unchanged, exactly as `ProfileRegistry.load` already expects; every other name resolves
  to one individual secret string, unchanged from today's `get_secret(name)` contract.
- **FR-007**: `AgeBackend.get_secret` MUST decrypt the vault at most once per process: the first
  call decrypts and caches the parsed mapping for the life of the process; every later call,
  including one for a different name, MUST be served from that cache with no further decrypt.
- **FR-008**: The decrypt subprocess's passphrase prompt MUST pass through to the controlling
  terminal untouched. No code in `headless/` or `scripts/` MUST capture, construct, store, log,
  or in any way come to hold the passphrase's characters.
- **FR-009**: `AgeBackend`'s constructor MUST accept an optional injectable runner callable so
  unit tests can exercise every branch without invoking the real `age` binary and without ever
  prompting for a passphrase.
- **FR-010**: A `get_secret` call for a name absent from the decrypted mapping MUST raise the
  existing `SecretMissing`, unchanged.
- **FR-011**: A `get_secret` call when the vault file does not exist MUST raise a config-style
  error naming only the resolved file path, never any vault content (there is none to name).
- **FR-012**: A failed decrypt (wrong passphrase, a corrupted or non-`age` file, or no
  controlling terminal available to prompt on) MUST raise a value-free error naming only
  `age`'s exit code, alongside one fixed hint string ("wrong passphrase, corrupted vault, or
  no terminal for the passphrase prompt"); the error MUST NEVER include any part of `age`'s
  own stderr output.
- **FR-013**: `AgeBackend.put_secret` and `AgeBackend.delete_secret` MUST raise a clear error
  directing the caller to `scripts/vault.py`; an errand script MUST NEVER be able to trigger a
  vault write or a surprise re-encrypt prompt chain.
- **FR-014**: `AgeBackend.self_test()` MUST check only that `age` resolves on `PATH` and that the
  vault file exists. It MUST NEVER decrypt and MUST NEVER prompt for a passphrase, so that
  `scripts/check_env.py` remains entirely prompt-free.
- **FR-015**: `scripts/check_env.py`'s vault row MUST report the `age` backend by name on
  success and, on failure, print a hint naming a platform-appropriate install command (`brew
  install age` on macOS, `winget install FiloSottile.age` on Windows, a generic
  package-manager hint elsewhere) when the binary is missing, or
  `python scripts/vault.py init` when the vault file is missing.
- **FR-016**: `scripts/vault.py init` MUST refuse to run, before invoking `age` at all, when the
  vault file already exists. Otherwise it MUST create a new, empty (`{}`) vault by encrypting
  through `age`, which prompts for the passphrase twice (enter, then confirm).
- **FR-017**: `scripts/vault.py set NAME` MUST read the value to store from hidden `getpass`
  input, never from `argv` and never from an environment variable, then decrypt the existing
  vault, update the in-memory mapping, and re-encrypt it atomically: a temporary file in the same
  directory, then `os.replace` onto the vault's path, at file mode `0600` where the platform
  supports it.
- **FR-018**: `scripts/vault.py unset NAME` MUST remove a name from the mapping the same atomic
  way as `set`, and MUST succeed whether or not the name was present.
- **FR-019**: `scripts/vault.py list` MUST print item names only, one per line, and MUST NEVER
  print a value.
- **FR-020**: `scripts/vault.py path` MUST print the resolved vault file path and MUST NOT invoke
  `age` or touch the vault file's contents.
- **FR-021**: Every `scripts/vault.py` subcommand that reads or writes the vault (`init` after its
  existence check, `set`, `unset`, `list`) MUST trigger its own passphrase prompt; no subcommand
  invocation MUST reuse a passphrase or a decrypted mapping cached by a previous invocation or
  process.
- **FR-022**: `scripts/vault.py` MUST run identically on macOS and Windows: plain `subprocess`
  calls to `age` resolved from `PATH`, `pathlib` for every path, and no pseudo-terminal tricks of
  any kind. A file-mode `0600` call that is a no-op on Windows MUST NOT raise there.
- **FR-023**: No backend (`age`, `keychain`, or `gcp`) MUST ever be used to store a password or a
  payment card value. The profile registry holds only the identifiers an errand types into a
  form (name, address, date of birth, PAN, VIN, driving licence and policy numbers, and similar);
  a login persists through the v0.0.3 session-cookie mechanism, and any payment action stays
  human-only per `CLAUDE.md`.
- **FR-024**: `errand.py`'s existing pre-resolution loop (every plan source resolved before any
  browser window opens, in every mode) MUST remain unchanged in shape. Because it now touches
  `AgeBackend` whenever the default backend is active, any errand whose plan includes a
  `secret:` or `registry:` source MUST prompt for the passphrase on every run, in every mode
  including preview and check, and therefore MUST require a real controlling terminal in every
  mode. `probe.py`'s empty plan MUST continue to trigger no decrypt and no prompt.

### Non-Functional Requirements

- **NFR-001**: No code path this feature adds, in `headless/` or `scripts/`, MUST ever read the
  passphrase into a Python variable, an environment variable, a log line, a preview artifact, or
  a file of any kind. `age`'s own terminal dialog is the only place the passphrase ever exists.
- **NFR-002**: The unit test suite MUST run to completion with zero passphrase prompts and zero
  invocations of the real `age` binary; every `AgeBackend` and `scripts/vault.py` test MUST use
  the injectable runner (FR-009) or an equivalent fake.
- **NFR-003**: A fresh clone that follows only the README's "First-time setup" section MUST reach
  `check_env.py` 5/5 PASS, with no guidance beyond that section consulted.
- **NFR-004**: Every note or exception message this feature introduces MUST be provably value-free:
  no message MUST ever contain a decrypted mapping's value, a passphrase character, or `age`'s raw
  stderr text.

### Key Entities

- **Vault file**: the single persisted artifact this feature introduces, one `age`-encrypted,
  ASCII-armored file per machine (default `~/.headless/profile.age`), holding one JSON object
  mapping item names to string values. Outside the repository by default; `.gitignore` excludes
  it as a second line of defense. Never holds a password or a payment card value (FR-023).
- **Vault item**: one named entry inside the decrypted mapping - either the `profile` item (a
  JSON-registry string, unchanged from today's `ProfileRegistry` contract) or any other named
  individual secret string. Never partially written: every `scripts/vault.py` write re-encrypts
  the whole mapping in one atomic operation.
- **AgeBackend**: the `VaultBackend` implementation this feature adds. Holds no state before its
  first `get_secret` call (locked); after that call, holds the decrypted mapping in memory for
  the rest of the process (decrypted-cached). Never itself performs a write; `put_secret` and
  `delete_secret` raise, directing the caller to `scripts/vault.py`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full unit suite (`python -m pytest -q`) completes with zero passphrase prompts
  and zero real `age` subprocess invocations, provable because every `AgeBackend`/`vault.py` test
  uses the injectable runner.
- **SC-002**: A unit test constructing an `AgeBackend` with a fake runner and calling
  `get_secret` twice for two different names proves exactly one decrypt invocation happened
  across both calls (FR-007).
- **SC-003**: A unit test proves `load_config()` with `HEADLESS_SECRETS_BACKEND` unset resolves
  `secrets_backend == "age"`.
- **SC-004**: A unit test proves `scripts/vault.py list`'s captured stdout, run against a fixture
  mapping with distinctive synthetic values, never contains any of those values - only names.
- **SC-005**: A unit test proves `AgeBackend.self_test()` never invokes the runner's decrypt path
  (`age -d`); it only checks `PATH` and file existence (FR-014).
- **SC-006**: A unit test proves `check_env.py`'s vault row prints a `brew install age` hint when
  the binary is absent and a `python scripts/vault.py init` hint when the vault file is absent,
  each under its own stubbed condition.
- **SC-007**: A unit test constructs a decrypt failure (nonzero exit) with a distinctive
  fixture-shaped stderr string and proves that string never appears in the raised exception's
  message - only the exit code and the fixed hint do (FR-012, NFR-004).
- **SC-008**: A unit test proves `scripts/vault.py set`/`unset` never place the value being
  stored on any subprocess's `argv`; the value reaches `age` only through piped stdin bytes
  constructed in memory.
- **SC-009**: A repository-wide grep for the string `"passphrase"` across `headless/` and
  `scripts/` finds it only in docstrings, comments, and printed hint text - never as the name of
  a variable holding a decrypted value (NFR-001, manual verification step recorded in
  quickstart.md).
- **SC-010**: Following only the README's "First-time setup" section on a fresh clone reaches
  `check_env.py` 5/5 PASS, confirmed by Director UAT on at least one macOS machine (NFR-003;
  quickstart.md records the exact walkthrough; this spec-authoring delivery does not execute it,
  since doing so would touch `~/.headless/`).

## Assumptions

- `age` 1.3.1 (installed via `brew install age` on this machine) is available as a single,
  dependency-free Go binary on every platform this feature targets: Homebrew on macOS, `winget`
  or `scoop` on Windows, and a system package on Linux, verified for macOS on this machine before
  this feature was scoped.
- `age -e -p -a -o <file> <input>` prompts twice ("Enter passphrase", "Confirm passphrase") on
  the controlling terminal (`/dev/tty`), and `age -d <file>` prompts once; a wrong passphrase
  exits nonzero with "incorrect passphrase" on stderr. All verified empirically, including a
  byte-exact round trip, before this feature was scoped.
- Because `age` prompts on `/dev/tty` directly rather than reading from the process's `stdin`,
  a Python `subprocess` call to it inherits the terminal for the prompt while `stdin` remains
  free for piping plaintext data to an encrypt call; the passphrase itself is never something
  Python's own code receives, sees, or could log even if it tried.
- There is no *packaged* macOS GUI for `age` (Homebrew has no cask for one, and the
  community's own `awesome-age` list had none for macOS when this feature was scoped); this
  feature's own implementation and its normative documentation stay entirely command-line. A
  young, independent, unpackaged third-party GUI, [Age Mac](https://github.com/vikiea/age_mac)
  (ad-hoc signed, DMG releases, opens the same vault file format `scripts/vault.py` writes),
  surfaced after that survey and is mentioned in the README's First-time setup section as a
  clearly optional, at-your-own-risk alternative to the command line - not something this
  feature builds, bundles, verifies, or depends on.
- The Director is the only person who runs this tool; the vault's threat model is the same
  single-user, local-machine model `CLAUDE.md`'s Secrets section already assumes for the
  Keychain backend today.
- Passphrase strength is the Director's own choice; this feature does not add or enforce any
  strength policy.

## Out of Scope

- Encrypting `session-cookies.json`: it already carries vault-grade classification inside the
  profile directory (`CLAUDE.md`'s Browser and Secrets sections); revisit only if the Director
  asks for it specifically.
- Building or bundling any GUI for the vault, on any platform: `scripts/vault.py` is the only interface this feature ships. (The README's optional mention of a third-party GUI, Age Mac, is a documentation pointer, not something this feature builds or maintains.)
- Activating any cloud secrets backend: the GCP Secret Manager plan is superseded by this
  feature; `GcpBackend`'s code stays in place, unused, and `terraform/README.md` records the
  supersession, but no cloud resource is created by this feature.
- Storing a password or a payment card value in any backend, ever (FR-023); this is a permanent
  policy this feature records, not a temporary scope boundary to revisit later.
- Any passphrase strength policy or enforcement: entirely the Director's own choice.
- Passphrase caching of any kind (an environment variable, a keychain item, a file, or a
  command-line flag): explicitly rejected, since it would defeat the per-run approval gate that
  is this feature's whole point (User Story 2).
