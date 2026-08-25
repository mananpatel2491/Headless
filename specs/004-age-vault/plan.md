# Implementation Plan: Age Vault

**Branch**: `v0.0.4` | **Date**: 2026-08-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-age-vault/spec.md`

## Summary

Replace the planned GCP Secret Manager backend with a local, open-source, passphrase-encrypted
vault built on `age`, and make it the default secrets backend. A new `AgeBackend`
(`headless/secrets.py`) decrypts the vault file at most once per process, caching the result in
memory; because `age` prompts for its passphrase on the controlling terminal directly, never
through Python's own `stdin`, the passphrase never enters this codebase at all. All writes route
through a new maintenance script, `scripts/vault.py` (`init`/`set`/`unset`/`list`/`path`);
`AgeBackend.put_secret`/`delete_secret` refuse, so an errand can never trigger a surprise
re-encrypt. `headless/config.py` gains the `age` backend value (made the default) and a new
`age_file` field. `scripts/check_env.py`'s vault row is extended to check `age` reachability and
vault-file existence only, never a decrypt, so it stays prompt-free. `README.md` gains a
"First-time setup" section covering macOS and Windows. Decisions are recorded in
[research.md](research.md) (D1-D10).

## Technical Context

**Language/Version**: Python 3.14 (venv per worktree, same as the rest of the repository)

**Primary Dependencies**: none new as a Python package. The feature depends on the external `age`
binary being present on `PATH` (verified: `age` 1.3.1 via `brew install age` on this machine;
`winget`/`scoop` on Windows, a system package on Linux) - not a `pip` dependency, not added to
`requirements.txt`. The vault file itself is read and written with the standard library only
(`subprocess`, `json`, `getpass`, `os.replace` for the atomic rename, `os.chmod` for the `0600`
mode).

**Storage**: one new persisted artifact, the vault file (default `~/.headless/profile.age`), an
`age`-encrypted, ASCII-armored text file holding one JSON object. Not a database, not versioned,
replaced whole on every write. Outside the repository by default (like `HEADLESS_PROFILE_DIR`
already is), and excluded a second time by a new `.gitignore` entry (`*.age`).

**Testing**: `pytest>=8` (already a dependency). Every `AgeBackend` and `scripts/vault.py` test
uses an injectable fake runner (spec FR-009) in place of the real `age` binary, so the unit suite
never invokes a subprocess that could prompt (spec NFR-002, SC-001). This matches the existing
convention `tests/test_secrets.py` already uses for `KeychainBackend`
(`monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)`) and `tests/test_check_env.py`
already uses for `_check_browser()`'s launch call.

**Target Platform**: cross-platform by design, unlike prior features in this repository. The
Director's macOS machine remains the primary target (Chrome 151, channel `chrome`, unchanged by
this feature), but `age`, `scripts/vault.py`, and the vault file's own mechanics are exercised
against no macOS-specific API - `subprocess`, `pathlib`, `json`, `getpass` are all standard
library and behave the same on Windows. Only the `0600` permission enforcement is
platform-conditional (no-op on Windows, documented in data-model.md and README).

**Project Type**: package change (`headless/secrets.py`, `headless/config.py`) plus one new
maintenance script (`scripts/vault.py`, following the Automation-First CLI pattern
`scripts/scan_secrets.py` and `scripts/check_env.py` already establish). No new errand. Single
project, same as v0.0.1 through v0.0.3.

**Performance Goals**: not a latency-sensitive path - a decrypt happens at most once per errand
run, and the Director is already expected to be at the keyboard for it (the gate is the point,
not an overhead to minimize). The unit suite covering `AgeBackend` and `vault.py`'s logic must
still run in well under a second combined (spec SC-001), since none of it touches a real
subprocess or a real passphrase prompt.

**Constraints**: the passphrase must never enter any Python variable, environment variable, log
line, or file (spec FR-008, NFR-001) - the entire feature is designed around `age`'s own
`/dev/tty` prompting behavior to make this true by construction, not by discipline; no plaintext
vault content may ever be written to disk, at any point in any operation (spec D4, D6); an errand
must never be able to trigger a vault write (spec FR-013); `check_env.py`'s vault row must never
decrypt or prompt (spec FR-014); every `scripts/vault.py` write must be atomic and end at file
mode `0600` (no-op on Windows); existing `KeychainBackend`/`GcpBackend` tests and behavior must
keep passing unmodified (spec FR-003).

**Scale/Scope**: two files materially changed (`headless/secrets.py`: new `AgeBackend` class,
`open_vault`'s dispatch gains the `age` branch; `headless/config.py`: `VALID_SECRETS_BACKENDS`
gains `"age"`, the default changes, a new `age_file` field and its resolution rule), one new
maintenance script (`scripts/vault.py`), one small matching change
(`scripts/check_env.py`'s `_check_vault` gains age-aware logic), one `.gitignore` line, new tests
across `tests/test_secrets.py`, a new `tests/test_vault.py`, and `tests/test_check_env.py`, plus
the docs-of-record updates listed in Project Structure below. No new cloud resource (the opposite:
one is explicitly not created - `terraform/README.md` records the supersession). No change to
`headless/errand.py`'s pre-resolution loop shape (spec FR-024): it already resolves every plan
source before any window opens, in every mode; this feature changes only which backend that loop
talks to by default.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated against the constitution as it stands today (1.2.1); this feature's own amendment to
1.3.0 is a Polish-phase task (tasks.md), not yet in effect for this check.

| Principle / rule | Status | Evidence |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | PASS | `Project_Structure.md` gains a v0.0.4 Changelog row naming every file touched, plus new rows for `headless/secrets.py`'s `AgeBackend` and `scripts/vault.py`, in the implementation commit (a tasks.md Polish task, not done in this spec-only run). |
| II. Pattern Reference Integrity | PASS | `PATTERNS.md` gains two entries at implementation time: "Age vault" and "Passphrase is the gate" (tasks.md Polish phase); this plan does not pre-empt their wording. |
| III. Automated Maintenance via Agentic Skills | PASS | `scripts/vault.py` is a new maintenance script following the Automation-First CLI pattern already governing `scripts/scan_secrets.py` and `scripts/check_env.py`: `argparse`, non-interactive (subcommand-driven, no hidden prompts beyond `age`'s own), a safe read-only `list`/`path` pair alongside the writing subcommands. |
| IV. Continuous Errand Validation | PASS | Pure logic (`AgeBackend`'s cache-after-first-decrypt behavior, its failure-mode error shapes, `vault.py`'s mutate-then-re-encrypt sequencing) gets unit tests with an injectable fake runner, matching the pattern `tests/test_secrets.py` already uses for `KeychainBackend`. There is no new site and no new `--check` mode to add - `vault.py` is a maintenance script, not an errand, the same carve-out `research.md` D8 in spec 002 and D6 in spec 003 both already used for a maintenance script with no site of its own. |
| V. Infrastructure-as-Code and Cost Gating | PASS, and this feature reduces exposure | No cloud resource is created; the opposite happens - the GCP Secret Manager plan this principle's own example clause names is explicitly superseded, and `terraform/README.md` gains a status paragraph recording that (tasks.md Polish phase). `GcpBackend`'s code is left in place but inert (D10: not deleted, not activated). |
| Gates hard rule (preview/apply/check, no submit) | PASS, unaffected | No new mode, no new flag, no path toward a submit/pay/verify/otp concept. This feature changes which backend a run's secrets come from, not what a run is allowed to do once it has one. |
| Secrets hard rule | PASS, directly extended, and one new sub-rule added | The vault file holds the same class of data (typed/session values) `CLAUDE.md`'s Secrets section already governs; `AgeBackend` never prints a value (spec FR-008, NFR-001, NFR-004), matching `redact()`'s existing convention where a value could ever reach a printable surface (it cannot here - nothing this feature adds ever holds a value in a printable form outside `get_secret`'s direct return). New: this feature also states, for the first time as an explicit rule rather than an implicit practice, that a password or a payment card value is never stored in any backend (spec FR-023) - `CLAUDE.md`'s Secrets section gains this sentence in Polish. |
| Browser hard rule | N/A | This feature touches no browser code path. |
| Spec-driven workflow | PASS | This feature runs specify only (this delivery) on `v0.0.4` in this worktree, per the mananUtils worktree protocol and this delivery's explicit brief (spec-authoring only; plan/tasks/implementation are separate, later runs under the Director's own PM-spec working style for work repositories - though Headless itself follows this repository's own CEO-autonomy Spec Kit chain once implementation is authorized). |

No violations; Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: the data model (`VaultDocument`, `AgeBackend`'s two
states, `vault.py`'s operation lifecycle) and the one new contract
(`contracts/vault-and-cli.md`) introduce exactly one new class (`AgeBackend`), one new script
(`scripts/vault.py`), and two small, additive changes to existing files
(`headless/config.py`'s `Config` dataclass, `scripts/check_env.py`'s `_check_vault`) - no new
abstraction beyond what the Technical Context already names. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/004-age-vault/
├── spec.md
├── plan.md                    # This file
├── research.md                # Phase 0: decisions D1-D10
├── data-model.md              # Phase 1: VaultDocument, AgeBackend states, vault.py lifecycle
├── quickstart.md              # Phase 1: the Director's UAT script
├── contracts/
│   └── vault-and-cli.md       # the vault file contract, AgeBackend behavior, the vault.py CLI
│                               # contract, check_env's row contract, the environment variable table
├── checklists/
│   └── requirements.md
└── tasks.md                   # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
headless/
├── secrets.py             # updated: AgeBackend class (get_secret/put_secret/delete_secret/
│                           #   self_test), open_vault's dispatch gains the "age" branch
└── config.py               # updated: VALID_SECRETS_BACKENDS gains "age" (made the default),
                             #   Config gains age_file: Path, its resolution and relative-path
                             #   refusal

scripts/
├── vault.py                # NEW: init / set NAME / unset NAME / list / path
└── check_env.py             # updated: _check_vault()'s age-backend branch (PATH + file
                              #   existence only, never a decrypt)

.gitignore                   # updated: *.age added as a belt-and-braces entry

tests/
├── test_secrets.py         # updated: AgeBackend unit tests against an injectable fake runner
│                             #   (decrypt-once-and-cache, every failure mode, put/delete refusal,
│                             #   self_test's no-decrypt contract), open_vault dispatch test
├── test_vault.py            # NEW: scripts/vault.py subcommand tests against the same fake
│                             #   runner seam (init refusal, set/unset atomic re-encrypt, list
│                             #   names-only, path, exit codes, no-value-on-argv proof)
└── test_check_env.py        # updated: the age-backend branch of _check_vault(), both hint
                              #   strings, under stubbed PATH/file-existence conditions

CLAUDE.md                    # updated: Secrets section - default backend statement, the
                              # per-run passphrase gate, the never-store-passwords-or-cards
                              # policy (tasks.md Polish)
.specify/memory/constitution.md   # updated: 1.2.1 -> 1.3.0 (MINOR: default backend changed,
                                   # one new explicit hard rule added)
PATTERNS.md                  # updated: two new entries ("Age vault"; "Passphrase is the gate")
README.md                    # updated: new "First-time setup" section (macOS and Windows);
                              # Setup section's existing secrets step updated for the new default
Project_Structure.md         # updated: v0.0.4 Changelog row, new Application Layer rows for
                              # scripts/vault.py and this feature's headless/ changes (this is
                              # also where the repository's version is recorded; no separate
                              # VERSION file exists, confirmed by the same grep spec 003's D8
                              # already ran)
MEMORY.md                    # updated: the Director's decision to supersede the GCP plan,
                              # dated 2026-08-25

.env.example                 # updated: HEADLESS_SECRETS_BACKEND comment reflects the new
                              # default; a new HEADLESS_AGE_FILE line with its default and rule
terraform/README.md          # updated: a status paragraph recording the supersession (Director
                              # decision 2026-08-25); no cloud resource created by this feature

headless/errand.py           # UNCHANGED - the pre-resolution loop's shape does not change
                              # (spec FR-024); it already resolves every plan source, in every
                              # mode, before any window opens
headless/gates.py            # UNCHANGED - no new mode, no new flag
headless/profile.py          # UNCHANGED - ProfileRegistry's contract with get_secret("profile")
                              # is unchanged (spec FR-006)
requirements.txt             # UNCHANGED - age is an external binary, not a pip dependency
requirements-gcp.txt         # UNCHANGED - GcpBackend's optional extra is untouched (D10: code
                              # stays in place, inert)
Function_Mapping.md          # UNCHANGED - this feature touches no errand's field mapping;
                              # scripts/vault.py is a maintenance script, not an errand, the
                              # same carve-out check_env.py and scan_secrets.py already have
```

**Structure Decision**: single project, same as every prior feature in this repository. Both the
new backend and the new CLI land next to the code they extend: `AgeBackend` inside
`headless/secrets.py`, the module that already owns `KeychainBackend`/`GcpBackend` and the
`open_vault` dispatch (`PATTERNS.md`'s "Secrets backend seam" entry) - there is no reason to
introduce a new module for a third `VaultBackend` implementation a single file already hosts two
of. `scripts/vault.py` is a new file because it is a genuinely new maintenance script, the same
way `scan_secrets.py` earned its own file in v0.0.2 rather than being folded into an existing one.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None.
