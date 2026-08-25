# Quickstart: Age Vault

**Feature**: 004-age-vault | **Date**: 2026-08-25

Runnable validation scenarios that prove the feature end-to-end, once implemented. Contracts are
in [contracts/vault-and-cli.md](contracts/vault-and-cli.md); entities in
[data-model.md](data-model.md).

**Every scenario below that runs a real `age` command touches `~/.headless/` (or wherever
`HEADLESS_AGE_FILE` points) and prompts for a real passphrase on a real terminal. This is
Director-run UAT, not something a builder or an automated agent executes on the Director's
behalf - the whole point of this feature is that a human has to be at the keyboard for it.**

## Prerequisites

- From the worktree root, the existing `.venv` (no new Python dependency):
  ```bash
  source .venv/bin/activate
  ```
- `age` on `PATH`. Install it if `age --version` fails:
  ```bash
  brew install age                              # macOS
  winget install FiloSottile.age                # Windows (or: scoop install age)
  ```

## Scenario 1: confirming age is reachable before a vault exists (US1, US3)

```bash
python scripts/check_env.py
```

Expected, before `vault.py init` has ever run: the `vault` row reads FAIL with the hint
`python scripts/vault.py init` (assuming `age` itself is already on `PATH`; if it is not, the
hint instead names the install command). Every other row's behavior is unchanged from v0.0.1
through v0.0.3.

## Scenario 2: creating the vault (US1, US3)

```bash
python scripts/vault.py init
```

Expected: `age`'s own `Enter passphrase` prompt, then `Confirm passphrase`. Choose a real
passphrase and remember it - there is no way to recover it, and no option to save it anywhere.
On success, `vault.py` prints the resolved path (for example `~/.headless/profile.age`). Running
`init` a second time refuses immediately, before any prompt, because the file already exists.

## Scenario 3: seeding the `profile` item (US1, US3)

```bash
python scripts/vault.py set profile
```

Expected: one passphrase prompt (decrypt), then a hidden `getpass` prompt for the value itself,
then `age`'s own enter/confirm pair (re-encrypt). Paste a small, obviously synthetic registry at
the hidden prompt, as one line, for example:

```json
{"identity": {"name": "Test Testerson", "pan": "ABCDE1234F"}, "address": {"home": {"line1": "1 Example Street"}}}
```

Never paste a real PAN, address, or any other real identifier here - this is a documentation
example, not a template to copy verbatim with real data still in place.

## Scenario 4: confirming the vault is reachable and correct (US1, US3)

```bash
python scripts/check_env.py
```

Expected: the `vault` row now reads PASS, naming the `age` backend. This step never decrypts
(spec FR-014) - it only confirms `age` is on `PATH` and the file exists, so it prompts for
nothing.

```bash
python scripts/vault.py list
```

Expected: one line, `profile`, and nothing else - never the JSON content set in Scenario 3. One
passphrase prompt (list always decrypts to read the names).

## Scenario 5: the passphrase gate on a real errand run (US2)

`probe.py`'s own field plan is empty, so it never touches the vault (spec FR-024) - running it
proves nothing about the gate. To see the gate fire, resolve a registry value directly:

```bash
python -c "
from headless.config import load_config
from headless.secrets import open_vault
from headless.profile import ProfileRegistry

vault = open_vault(load_config())
registry = ProfileRegistry.load(vault)
print(registry.get('identity.name'))
"
```

Expected: exactly one passphrase prompt (the vault's first `get_secret` call, triggered by
`ProfileRegistry.load`), then the value from Scenario 3's example prints. Run the same snippet
again in the same shell (a new process) and the prompt appears again - nothing about a passphrase
is ever cached between runs (spec FR-021's sibling guarantee for `AgeBackend` itself, spec D5's
"decrypt once per process, never across processes").

A real errand whose field plan includes a `registry:` or `secret:` source (the shape a future
feature like ITR-portal-walk spec 005 would use) triggers this same single prompt the first time
its pre-resolution loop touches the vault, in every mode including `preview` and `--check` (spec
FR-024) - not only `--apply`.

## Scenario 6: wrong passphrase (US2)

Repeat Scenario 5's snippet, but type the wrong passphrase at the prompt.

Expected: the run refuses with a value-free error naming only `age`'s exit code and the fixed
hint `wrong passphrase, corrupted vault, or no terminal for the passphrase prompt` - never `age`'s own stderr text, never any byte of the
vault's content.

## Scenario 7: unit-level proof, zero prompts (SC-001, SC-002, SC-005, SC-007, SC-008)

```bash
python -m pytest -q tests/test_secrets.py tests/test_vault.py -k age
python -m pytest -q tests/test_check_env.py -k vault
```

Expected: every `AgeBackend` and `vault.py` test passes with zero passphrase prompts and zero
invocations of the real `age` binary - every test uses the injectable fake runner. This run
should feel identical, in kind, to the existing `KeychainBackend` tests in `tests/test_secrets.py`
(`monkeypatch.setattr("headless.secrets.subprocess.run", fake_run)`), just for a different
backend.

## Scenario 8: no value ever reaches argv (SC-008)

```bash
python -m pytest -q tests/test_vault.py -k argv
```

Expected: a test proving `scripts/vault.py set`'s value never appears as a constructed
subprocess argument passes - the value only ever reaches `age` through piped `stdin` bytes.

## Scenario 9: never store a password or a card (FR-023, D8)

There is no automated test that can prove a negative about what the Director chooses to type into
`vault.py set`. This scenario is a policy reminder, not a mechanical check: `vault.py set` never
validates or rejects a value by shape (spec Out of Scope: no passphrase-or-value strength policy),
so nothing technically stops a password from being typed in. The safeguard is `CLAUDE.md`'s
amended Secrets section (Polish phase) stating the policy plainly, and the fact that every login
this tool needs already persists through the v0.0.3 session-cookie mechanism instead, so there is
never a reason to type one in here in the first place.

## Scenario 10: the fresh-clone walkthrough (US3, SC-010)

Follow `README.md`'s "First-time setup" section top to bottom on a machine with nothing
Headless-specific installed - macOS or Windows. The section's own final step is
`python scripts/check_env.py`; a 5/5 PASS there, with the `vault` row naming the `age` backend, is
this scenario's pass condition. Record the machine (macOS or Windows) and the outcome in
`MEMORY.md`'s "Errands run" table the same way v0.0.1 and v0.0.3's own UAT rows are recorded -
site/tool name only, never any value that was typed during setup.

## Scenario 11: commit gate (all user stories)

```bash
python -m pytest -q
python scripts/verify_structure.py
git add -A
python scripts/scan_secrets.py --staged
```

Expected: the full unit suite passes (including this feature's new tests), `verify_structure.py`
reports SUCCESS with every changed/new file accounted for in `Project_Structure.md`'s Changelog,
and `scan_secrets.py --staged` reports clean - every fixture value this feature's own tests use
(a fake vault document, a fake passphrase-shaped string used only to prove it never leaks) must be
obviously synthetic, never shaped like a real credential, the same rule spec 002's and spec 003's
own quickstart scenarios already state for their fixtures.
