# Agentic Skills (scripts/)

Two kinds of script live here: **maintenance** scripts that keep the repo honest, and
**errand** scripts that drive a site on the Director's behalf. Both follow the
Automation-First CLI pattern (`PATTERNS.md`): `argparse`, safe preview by default, runnable
from cron or CI.

## Maintenance

| Script | Description |
| :--- | :--- |
| `verify_structure.py` | Fails (exit 1) when a file on disk is missing from the `Project_Structure.md` Changelog. Part of the commit gate. `--dry-run` prints a read-only notice. |
| `check_env.py` | Environment self-test: Chrome (`chrome` channel), Playwright runtime + browser cache, profile directory, secrets vault, and (specs/002-commit-safety-gate) `core.hooksPath` activation. Prints PASS/FAIL/SKIP per row; opens no browser window. Not a browser errand; the errand contract below does not apply (no preview/apply/check modes, no `HANDOFF`). Usage: `python scripts/check_env.py`. |
| `scan_secrets.py` | Commit safety gate (specs/002-commit-safety-gate): credential and personal-identifier scanner, standard library only, runs under the macOS system `python3` as well as the project's `.venv`. Not a browser errand; never opens a browser or writes anything. Four mutually exclusive modes: `--staged` (added lines of `git diff --cached`, used by `.githooks/pre-commit`), `--paths FILE [FILE ...]` (complete content of named files), `--history` (every blob reachable from `HEAD`, used by the CI backstop), `--stdin-hook` (reads a Claude Code `PreToolUse` payload from stdin, used by `.claude/settings.json`). Exit `0` clean / `1` findings / `2` usage error in the first three modes; `--stdin-hook` always exits `0` and communicates a deny through its own JSON output (fail-open on anything it cannot parse). See `contracts/cli-and-hooks.md` for the full contract and `.scanignore` for the allowlist grammar. |
| `vault.py` | The local age-encrypted vault CLI (spec 004-age-vault): the only place the vault is ever written. Not a browser errand; never opens a browser. Subcommands: `init` (refuses if the vault file already exists), `set NAME` (value read via hidden `getpass`, never `argv`), `unset NAME` (idempotent), `list` (item names only, never values), `path` (resolved vault file path, no `age` invocation). Every read-or-write subcommand triggers its own passphrase prompt; nothing is cached across invocations. Exit `0` success / `1` a vault-level refusal / `2` a usage error. Usage: `python scripts/vault.py {init,set,unset,list,path} [NAME]`. See `specs/004-age-vault/contracts/vault-and-cli.md` for the full contract. |

## Errands

| Script | Description |
| :--- | :--- |
| `probe.py` | Open a URL in the Headless profile and write a preview artifact; prints the page title. Read-only (`HANDOFF = "n/a (read-only errand)"`); `--apply` still performs the handoff with an empty plan so the Director can seed a login. Usage: `python scripts/probe.py <URL> [--apply|--check] [--profile-dir PATH] [--headless] [--preview-dir PATH] [--no-screenshot]`. |

## Errand contract

Every errand script:

1. Opens with a docstring stating the site, the background, the handoff point, and the
   secrets and profile fields it needs.
2. Declares `HANDOFF = "<the step the human takes>"` as a module constant.
3. Runs in **preview** mode with no flags (no site writes; artifact under `previews/`),
   in **check** mode with `--check` (read-only selector probe), and in **apply** mode with
   `--apply` (fills up to `HANDOFF`, then leaves the window open and prints "Your turn").
4. Never implements a submit, pay, e-verify, or OTP step.
