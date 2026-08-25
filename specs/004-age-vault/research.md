# Research: Age Vault

**Feature**: 004-age-vault | **Date**: 2026-08-25

All Technical Context unknowns are resolved below. D1-D10 mirror the decisions the orchestrator
made and fixed before this feature entered planning; they are not re-opened here, only recorded
with their evidence and the alternatives that were considered and rejected, the same shape
`specs/003-login-persistence/research.md` already established for this repository.

## Verified facts, confirmed before this feature was scoped

The orchestrator verified the following on this machine (macOS) before any design decision below
was made:

- `age` 1.3.1 is installed via `brew install age`: a single, dependency-free Go binary, with
  packaged builds for Windows (`winget install FiloSottile.age`, `scoop install age`) and every
  common Linux distribution.
- `age -e -p -a -o file.age input` prompts `Enter passphrase` then `Confirm passphrase` on the
  **controlling terminal** (`/dev/tty`), not on the process's `stdin`.
- `age -d file.age` prompts once (`Enter passphrase`).
- A wrong passphrase at decrypt exits `1` with `incorrect passphrase` on stderr.
- A full encrypt-then-decrypt round trip was verified byte-exact on this machine.
- Because `age` prompts on `/dev/tty` itself rather than reading the prompt response from
  `stdin`, a Python `subprocess` call to it inherits the terminal for the prompt exchange while
  `stdin`/`stdout` remain completely free for the program's own use - piping plaintext in for an
  encrypt, or capturing plaintext out of a decrypt. **The passphrase never passes through Python
  in any form; Python cannot see it, store it, or log it, even by mistake.** This is the entire
  headline security property this feature is built on.
- Homebrew has no cask for an `age` GUI on macOS, and the community-maintained `awesome-age` list
  has no macOS GUI listed either (the one Windows-only GUI, Winage, does not apply here). No GUI
  is mentioned anywhere in this feature's design or documentation as a result.

This is the evidence base for D1 through D7.

## D1. Backend: a new `age` value, made the default

- **Decision**: `VALID_SECRETS_BACKENDS` gains `"age"`. `HEADLESS_SECRETS_BACKEND` unset now
  resolves to `"age"` (today's default, `"keychain"`, changes). `KeychainBackend` stays available
  and unmodified (macOS only, still selectable). `GcpBackend`'s code stays in the tree, unused;
  its activation plan is superseded.
- **Rationale**: the Director's own decision (2026-08-25) replaced the GCP Secret Manager plan
  with a local, open-source vault. Making `age` the default - not merely an option next to
  `keychain` - is what actually retires the GCP plan in practice: a default that stays
  `"keychain"` would leave every future clone defaulting to a macOS-only backend for a tool the
  Director explicitly wants to be settable up "on their own machine, macOS or Windows."
  `KeychainBackend` is left exactly as it is (still useful on macOS, still exercised by its own
  existing tests) because nothing about this feature requires removing a working, already-tested
  backend; deleting it would be scope this feature was never asked to take on.
- **Alternatives considered**: GCP Secret Manager plus Privileged Access Manager, the plan this
  feature supersedes (rejected by the Director: PAM requires a human to approve each access
  grant, and Google's own policy forbids a principal approving its own grant - a single-Director
  tool would need a second Google account solely to hold the approver role, on top of a standing
  cloud dependency and its monthly cost, for a problem a local file can solve for free); leaving
  `"keychain"` as the default and adding `"age"` only as an opt-in (rejected: the Director's own
  brief was explicit that the vault should be "available locally" for "anyone" cloning the
  repository, and a Windows clone has no Keychain to fall back to at all - `age` has to be the
  default for the cross-platform claim in User Story 3 to hold).

## D2. Vault file: derived default, one narrow override

- **Decision**: `Path(config.age_file)`, resolved from `HEADLESS_AGE_FILE` when set, defaulting
  to `~/.headless/profile.age`. After `~`-expansion the value MUST be absolute; a value that
  remains relative raises `ConfigError`, the same refusal `HEADLESS_PREVIEW_DIR` already applies
  to a relative override outside its one literal exception. `.gitignore` gains `*.age` as a
  belt-and-braces entry.
- **Rationale**: the vault, like the Chrome profile directory, has exactly one correct location
  for a given machine; a relative override would resolve differently depending on the current
  working directory of whatever process happens to read it, which is exactly the failure mode
  `preview_dir`'s existing rule was written to close (`headless/config.py`'s own comment: "any
  OTHER relative value is rejected outright ... a relative override could otherwise land
  anywhere"). Unlike `profile_dir`, which today has no such check, the vault file gets the
  stricter treatment because a misresolved profile directory merely seeds a login in the wrong
  place; a misresolved vault path could mean a script decrypts, or worse writes, a file the
  Director did not intend to touch. `.gitignore`'s `*.age` entry mirrors v0.0.3's
  `session-cookies.json*` entry exactly: the file already lives outside the repository by
  default, and the glob is a second line of defense for anyone who points the override inside it
  anyway.
- **Alternatives considered**: reusing `HEADLESS_PROFILE_DIR` as the vault's parent directory
  (rejected: the Chrome profile directory and the vault serve unrelated purposes and have
  unrelated threat models - the profile directory holds Chrome's own cookie database and this
  feature's session-cookie file, not credential material the Director types by hand; conflating
  the two locations would make a future change to one policy risk silently changing the other);
  applying `profile_dir`'s current, more permissive relative-path handling instead of
  `preview_dir`'s stricter one (rejected: nothing about the vault's location should ever be
  ambiguous, and the stricter rule costs nothing since the default already resolves absolute).

## D3. Vault content: one JSON object, unchanged consumer contract

- **Decision**: the decrypted vault is exactly one JSON object mapping each item name to a
  string value. `get_secret("profile")` keeps returning the registry JSON string
  `ProfileRegistry.load` already parses; every other name resolves to one individual secret
  string. One decrypt serves every `get_secret` call for the life of a process (D4).
- **Rationale**: `ProfileRegistry.load(vault, item="profile")` and every existing caller of
  `get_secret(name)` already assume "one string in, one string out" per name; changing that
  contract would ripple into `headless/profile.py`, `headless/errand.py`, and every existing test
  that constructs a `FakeVault`. Keeping the contract identical means this feature is purely a
  new `VaultBackend` implementation, not a change to anything that consumes one.
- **Alternatives considered**: a richer on-disk shape (nested objects, metadata, a version field)
  the way v0.0.3's `SessionCookieState` deliberately stays a bare array with no wrapper (rejected
  for the same reason that precedent gives: there is no caller today that needs anything beyond
  "name maps to one string", and adding structure nothing consumes yet would be speculative);
  one `age`-encrypted file per item, mirroring how the Keychain stores one item per name
  (rejected: that would mean a passphrase prompt per secret name instead of per run, defeating
  D4's single-decrypt-per-process property and multiplying how often the Director has to type the
  passphrase for no benefit).

## D4. `AgeBackend`: decrypt once, cache, never write

- **Decision**: `AgeBackend.get_secret`'s first call runs `age -d <vault_file>` with stdout
  captured entirely in memory, parses it as JSON, and caches the resulting dict for the rest of
  the process; every later call, for any name, reads the cache. The constructor accepts an
  optional injectable `runner` callable (FR-009) so tests never invoke the real binary. Plaintext
  is never written to disk and never printed, at any point. A missing vault file raises a
  config-style error naming only the path. A failed decrypt raises a value-free error naming
  only `age`'s exit code, plus the fixed hint "wrong passphrase or corrupted vault" - never any
  fragment of `age`'s own stderr. `put_secret`/`delete_secret` raise, pointing the caller at
  `scripts/vault.py` (D7). `self_test()` checks only `PATH` and file existence - never a decrypt.
- **Rationale**: decrypting once per process, not once per `get_secret` call, is what makes User
  Story 2's gate liveable: an errand whose plan touches three different registry paths still
  prompts the Director exactly once, not three times. Capturing stdout in memory rather than
  writing it to a temp file keeps the plaintext mapping off disk for the entire time it exists in
  this process - the same "no plaintext at rest beyond the encrypted file" property the vault
  exists to provide, applied to the decrypted copy in RAM as well. Never printing `age`'s own
  stderr matters for the same reason `research.md` D4 in spec 003 never printed a caught
  exception's message: `age`'s stderr on some failure paths could, in principle, echo back
  something about the file it was trying to read, and the class-name-and-fixed-hint convention
  this feature borrows from that precedent closes that door without needing to audit every
  version of `age`'s own error text for safety.
- **Alternatives considered**: decrypting on every `get_secret` call (rejected: multiplies
  passphrase prompts per run for no benefit, and directly works against User Story 2's own
  "prompts exactly once" acceptance scenario); writing the decrypted plaintext to a temp file
  before parsing it (rejected: `age -d`'s own stdout is already exactly the bytes needed, and a
  temp file would be one more thing this feature would have to prove is deleted, at zero benefit
  over capturing stdout directly into a Python `bytes` object that a `try`/`finally` never needs
  to unlink because it was never written); relaying `age`'s stderr in the raised error for easier
  debugging (rejected for the same reason spec 003's D4 rejected relaying a caught exception's
  message: the whole point of NFR-004 is that nothing about the vault's content or the failure's
  detail is ever in a printed or raised string, and a hint that never changes is exactly as
  debuggable as a stderr fragment without the same risk of quoting something back).

## D5. `scripts/vault.py`: the only write path, Automation-First CLI

- **Decision**: a new maintenance script, `scripts/vault.py`, is the only place the vault is ever
  written. Subcommands: `init` (refuses if the file exists; otherwise creates an empty `{}`
  vault, two prompts), `set NAME` (hidden `getpass` input, never `argv`; decrypt, mutate the
  in-memory dict, re-encrypt), `unset NAME` (same shape, removes a name), `list` (names only,
  never values), `path` (prints the resolved path, no `age` invocation at all). Every
  read-or-write subcommand triggers its own passphrase prompt; nothing is cached across
  invocations.
- **Rationale**: `PATTERNS.md`'s Automation-First CLI pattern already governs every script in
  `scripts/` (`argparse`, non-interactive flags, a safe default); `vault.py` follows it with
  subcommands instead of the mutually exclusive top-level flags `scan_secrets.py` uses, because
  `init`/`set`/`unset`/`list`/`path` are five genuinely different operations on the same
  resource, not five modes of scanning the same input. Routing every write through one script,
  never through an errand, is what makes FR-013's "an errand must never trigger a surprise
  re-encrypt" true structurally rather than by convention: `AgeBackend.put_secret` raises instead
  of writing, so there is no code path inside an errand that could even attempt it.
- **Alternatives considered**: giving `AgeBackend.put_secret` a real implementation, mirroring
  `KeychainBackend.put_secret` (rejected: `KeychainBackend.put_secret` is a single OS call with no
  passphrase prompt of its own; an `AgeBackend.put_secret` would mean any errand that happened to
  call it could trigger an unplanned decrypt-mutate-re-encrypt cycle, with its own prompt, in the
  middle of a run nobody reviewed for that - exactly the "surprise re-encrypt prompt chain" D7
  rules out); a single `set`/`get` pair of flags on one script instead of named subcommands
  (rejected: five distinct operations, one of which - `init` - has an entirely different
  precondition check than the rest, read better as named subcommands than as flag combinations).

## D6. `scripts/vault.py`'s write mechanics: plaintext never touches disk, atomic replace, cross-platform

- **Decision**: every write (`init`, `set`, `unset`) builds the new plaintext JSON mapping
  entirely in memory, pipes it to `age -e -p -a -o <target>` via the child process's `stdin`
  (never a temp plaintext file), captures the resulting ciphertext from `stdout`, writes that
  ciphertext to a temporary file in the vault's own directory, then atomically replaces the
  vault's path with it (`os.replace`) and sets file mode `0600` - the same
  decrypt-mutate-atomic-re-encrypt shape `headless/session.py`'s
  `_export_session_cookies` already established for `session-cookies.json` in v0.0.3. On
  Windows, the `chmod 0600` call is a documented no-op (Windows' own ACL model does not have a
  POSIX mode bit) and MUST NOT raise there.
- **Rationale**: piping plaintext through `stdin` rather than writing it to a temporary file
  before encrypting extends D4's "plaintext never touches disk" property to the write path too:
  because `age` reads its passphrase prompt from `/dev/tty` rather than `stdin` (the verified
  fact this whole feature is built on), `stdin` is completely free for the plaintext payload with
  no conflict between the two. Reusing v0.0.3's exact atomic-write shape (temp file in the same
  directory, `os.replace`, explicit `0600`) rather than inventing a new one means this feature
  inherits a pattern already reviewed, already tested, and already proven correct on this
  codebase, instead of asking a reviewer to re-verify a second atomic-write implementation doing
  the same job. The Windows no-op note exists because `os.chmod`'s mode argument is only
  partially meaningful there; documenting it as an accepted platform difference, rather than
  silently swallowing an exception that would never fire on a modern Windows filesystem in
  practice, is more honest than pretending the guarantee is identical on both platforms.
- **Alternatives considered**: writing the plaintext to a temporary file, then feeding that file
  to `age` as its input argument, then deleting the temp file (rejected: an unlink is not a
  guarantee against every failure mode - a crash between the write and the unlink would leave a
  plaintext file on disk - whereas piping through `stdin` means no plaintext file can exist at
  any point, crash or not); skipping the atomic replace and writing the target path directly
  (rejected: an interrupted direct write could leave a truncated, undecryptable vault file behind
  with no way to recover the previous version, exactly the failure mode v0.0.3's own atomic-write
  entry in `PATTERNS.md` already exists to prevent for `session-cookies.json`).

## D7. `check_env.py`'s vault row: reachability only, never a decrypt

- **Decision**: `check_env.py`'s vault row, when the active backend is `age`, reports PASS only
  when `age` resolves on `PATH` and the vault file exists; it never calls `age -d` and never
  prompts. On failure it names the specific missing piece: `brew install age` when the binary is
  absent, `python scripts/vault.py init` when the file is absent.
- **Rationale**: `check_env.py` is documented, and tested (`tests/test_check_env.py`), as a
  self-test that opens no browser window and completes in about a second; today's `vault` row
  achieves that for the Keychain backend by doing a real put/get/delete round trip that needs no
  human interaction. An `age`-backed vault row that decrypted for real would break that property
  outright - `check_env.py` would suddenly need someone standing at the terminal every time it
  runs, which is a materially different tool than the one `CLAUDE.md`'s Lesson 4 describes
  running "before trying a real errand." Checking existence and `PATH` reachability instead is
  the honest self-test for a backend whose entire design goal is that reaching it requires a
  human: `check_env.py` can prove the vault is *reachable* without proving it is *readable*, and
  proving the latter would mean giving up the very property this feature is built to guarantee.
- **Alternatives considered**: a `--with-vault-check` opt-in flag that does perform a real decrypt
  (rejected: adds a flag to a script whose whole documented value is running unattended before an
  errand, for a check whose only payoff is confirming something `vault.py list` already confirms
  interactively, at the cost of one more flag to explain in `scripts/README.md`); skipping the
  vault row entirely for the `age` backend (rejected: `check_env.py`'s five-row shape
  [`browser`, `playwright`, `profile_dir`, `vault`, `git_hooks`] is itself a documented contract
  `tests/test_check_env.py` already asserts against via `ROW_NAMES`; dropping a row for one
  backend would need its own special case in every place that iterates `ROW_NAMES`, for a check
  that a lighter existence probe already covers just as usefully).

## D8. Policy of record: passwords and cards are never stored

- **Decision**: no backend - `age`, `keychain`, or `gcp` - ever stores a password or a payment
  card value. The profile registry holds only identifiers an errand types into a form (name,
  address, date of birth, PAN, VIN, licence and policy numbers, and similar). A login persists
  through the v0.0.3 session-cookie mechanism instead of a stored password; any payment action
  stays human-only per `CLAUDE.md`'s existing "Terminal actions are human-only" rule. This
  feature's implementation phase amends `CLAUDE.md`'s Secrets section to state the policy
  explicitly and regenerates `.specify/memory/constitution.md` to **1.3.0** (MINOR: a materially
  changed default backend plus a new, explicit hard rule - not merely a wording change, unlike
  v0.0.3's PATCH bump).
- **Rationale**: this was a direct Director decision recorded in this feature's brief, not
  something this research phase had to derive - it is recorded here as policy of record because
  the constitution amendment task in Polish needs a decision to point at, the same way spec 003's
  D8 recorded its own docs-of-record decision before the actual edits happened. A MINOR bump
  (rather than PATCH, unlike v0.0.3's own bump) is correct because this feature changes the
  Secrets hard rule's concrete default (the backend a fresh clone gets with no configuration) and
  adds a rule that did not exist in any form before ("never store a password or a card value"),
  which the constitution's own Governance section treats as more than wording.
- **Alternatives considered**: treating "never store passwords or cards" as an assumption rather
  than a functional requirement (rejected: it is testable and user-observable - the profile
  registry's own shape either contains a password-shaped field or it does not - so it belongs in
  the numbered Functional Requirements, not the Assumptions section, the same reasoning spec
  003's checklist gave for keeping its own testable, non-implementation-detail language in the
  requirements list).

## D9. Documentation of first-time setup

- **Decision**: this feature's implementation phase (Polish, not this spec-authoring delivery)
  adds a "First-time setup" section to `README.md` covering both macOS and Windows: installing
  `age` (`brew install age` on macOS; `winget install FiloSottile.age` or `scoop install age` on
  Windows, presented as alternatives since this repository's CI does not verify either), the
  Python virtual environment and `playwright install chromium` step already documented, the
  commit-safety git hook activation step already documented, `python scripts/vault.py init` and
  `python scripts/vault.py set profile` with a minimal, obviously synthetic example registry, and
  `python scripts/check_env.py` as the section's own finish line. The section notes that the
  Keychain backend is macOS-only and that `age` is the cross-platform default for exactly that
  reason.
- **Rationale**: User Story 3 exists because the Director explicitly asked that "anyone cloning
  it can set up on their own machine, macOS or Windows" - a design decision recorded only in
  `research.md` and never surfaced in `README.md` would not satisfy that ask at all; the whole
  point is that the setup path is encoded in the repository's own front door, not in a document a
  new clone has no reason to open first.
- **Alternatives considered**: a separate `SETUP.md` file instead of extending the existing
  README (rejected: `README.md`'s existing "Setup" section already carries steps 1-6 for exactly
  this walkthrough; a second file would fork the setup instructions into two places that could
  drift, and `Project_Structure.md`'s Director Layer table already documents `README.md` as "the"
  setup and usage document - a second one would need its own entry and its own reason to exist
  that this feature does not have).

## D10. Out of scope

- **Decision**: this feature does not encrypt `session-cookies.json` (already vault-grade in the
  profile directory; revisit only on a future Director request), does not build or document any
  GUI on any platform, does not activate any cloud secrets backend (the GCP plan is superseded,
  not deleted - `GcpBackend`'s code stays in the tree, and `terraform/README.md` gains a status
  paragraph recording the supersession, but no cloud resource is created), and does not add any
  passphrase strength policy (entirely the Director's own choice, unchanged from any other
  password he sets for anything else).
- **Rationale**: each of these was named explicitly in the brief this feature was scoped from, as
  a boundary already decided rather than a question this research phase needed to resolve, the
  same shape spec 003's own D9 used for its own out-of-scope items.
- **Alternatives considered**: deleting `GcpBackend`'s code outright now that its activation plan
  is superseded (rejected: the code is inert, already lazily imported so it costs nothing to
  leave in place, still passes its own existing tests, and deleting working, tested code that
  nothing currently depends on removing is exactly the kind of scope this feature was not asked
  to take on - `terraform/README.md`'s status paragraph is enough to record that the plan will
  not be executed, without also demanding a code deletion in the same change).
