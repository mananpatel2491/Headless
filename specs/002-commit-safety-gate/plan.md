# Implementation Plan: Commit Safety Gate

**Branch**: `v0.0.2` | **Date**: 2026-08-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-commit-safety-gate/spec.md`

## Summary

Deliver one credential-and-PII scanner, `scripts/scan_secrets.py`, and wire it into every point
a change can reach public history: a local git pre-commit hook (`.githooks/pre-commit`), a
Claude Code write-time `PreToolUse` hook (`.claude/settings.json`), and a CI backstop
(`.github/workflows/secret-scan.yml`) that also runs `gitleaks` as a second, independent check.
An allowlist (`.scanignore` plus an inline `# scan:allow` marker) lets the Director exempt known
-safe test fixtures without weakening detection elsewhere. The scanner is Python standard-library
only, so every layer works on a fresh clone with no install step beyond what the project already
needs. Decisions are recorded in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.14 (venv per worktree, same as the rest of the repository)

**Primary Dependencies**: none new. `scripts/scan_secrets.py` uses only the Python standard
library (`re`, `json`, `argparse`, `subprocess` for `git diff --cached`/`git cat-file`,
`hashlib` is not needed - Luhn is arithmetic). It deliberately does **not** import
`headless.config` or any other `headless/` module: `config.py` pulls in `python-dotenv`, a
third-party dependency, which would break the zero-install guarantee for `--stdin-hook` and
`--staged` (both must work before `pip install -r requirements.txt` has ever run on a fresh
clone, since the pre-commit hook and the Claude Code hook are the first things that should be
active on it).

**Storage**: none. The scanner reads tracked git content (`git diff --cached`, commit blobs) and
`.scanignore`; it writes nothing, ever, in any mode.

**Testing**: `pytest>=8` (already a dependency); one new module, `tests/test_scan_secrets.py`,
entirely browser-free and dependency-free beyond a temporary git repository fixture for the
`--staged` and `--history` proofs.

**Target Platform**: cross-platform by construction (stdlib only) - the pre-commit hook and the
Claude Code hook run on the Director's macOS machine; the CI backstop runs on `ubuntu-latest`.
Nothing in this feature is macOS-specific, unlike the existing Keychain-backed secrets backend.

**Project Type**: CLI script (maintenance, not an errand - no site, no `HANDOFF`, same category
as `scripts/check_env.py`) plus hook/workflow configuration. Single project.

**Performance Goals**: a full-tree `--history` scan under 2 seconds (SC-006); the `--stdin-hook`
path adds no perceptible delay to a Claude Code write (its own hook `timeout` is set to 10
seconds as a ceiling, not a target); `--staged` on an ordinary commit-sized diff is effectively
instant.

**Constraints**: zero additional install for any of the three enforcement layers (D1); no raw
finding value in any output, in any mode, ever (FR-007, SC-005); `--stdin-hook` must never exit
non-zero or crash the assistant's turn, even on malformed input (FR-012, D1's corrected
behavior); the CI backstop must cost $0 on a public repository (constitution Lesson 5).

**Scale/Scope**: one new maintenance script, one hook file, one CI workflow, one allowlist file,
one Claude Code settings file, one test module; six documents of record updated (D9); no change
to `headless/` package code, no new errand, no new cloud resource.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / rule | Status | Evidence |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | PASS | `Project_Structure.md` gains Director-layer rows for `.githooks/`, `.github/`, `.scanignore`, `.claude/settings.json` and a v0.0.2 Changelog row listing every new file, in the implementation commit (D9). |
| II. Pattern Reference Integrity | PASS | `PATTERNS.md` gains one new "Commit safety gate (v0.0.2)" entry, and this feature's own scanner directly instantiates the already-registered **Cross-Platform Automation** pattern ("Maintenance and errand scripts are Python with `argparse`... "Spec Kit helper scripts are the Python variant") rather than introducing a competing convention - see the Cross-Platform pattern row below. |
| III. Automated Maintenance via Agentic Skills | PASS, with a scoped exception | `scan_secrets.py` is a maintenance script (like `check_env.py`), Python, `argparse`-driven, non-interactive, cross-platform. It does not follow "preview-by-default" the way an *errand* does, because it is not an errand: it never writes to any site or file in any mode, so there is no destructive default to guard against - its four modes differ only in what they read, not in whether they act. |
| IV. Continuous Errand Validation | PASS, mapped from errand to maintenance script | `scan_secrets.py` has no site and no `HANDOFF`, so the errand contract's "`--check` proves selectors resolve against a live site" does not apply verbatim (same carve-out `scripts/README.md` already documents for `check_env.py`). Its equivalent proof is `tests/test_scan_secrets.py` (D8): every pattern proven on a synthetic sample, proven to stop firing once allowlisted, without ever needing a live secret. `pytest` and `verify_structure.py` remain the commit gate; this feature adds to what they cover, it does not bypass them. |
| V. IaC and Cost Gating | PASS | No cloud resource created. The CI backstop (`secret-scan.yml`, `gitleaks-action@v2`) runs on GitHub-hosted minutes, free for a public repository on a personal account (D7); `terraform/README.md` is unchanged. |
| Gates hard rule (preview/apply/check, no submit) | N/A | This hard rule governs *errand* scripts that drive a browser. `scan_secrets.py` drives no browser and has no apply/submit concept at all; it is read-only in every mode by construction. |
| Secrets hard rule | PASS, directly extended | This feature exists to enforce "secrets and personal profile values never live in the repository" at the commit surface itself, closing the gap between the rule being written down and it being mechanically checked. Its own output obeys the same masking convention `headless/preview.py`'s `redact()` already established (`"****" + value[-2:]`), so the Director sees one consistent masking shape across the whole repository. |
| Browser hard rule | N/A | `scan_secrets.py` never opens a browser, a Chrome profile, or a `Session`. |
| Spec-driven workflow | PASS | This feature runs specify -> plan -> tasks -> implement on `v0.0.2` in a worktree, per the mananUtils worktree protocol. |
| Cross-Platform Automation pattern (PATTERNS.md) | PASS | `scan_secrets.py` is `argparse`-based, standard-library only, and behaves identically on the Director's macOS machine and the CI job's `ubuntu-latest` runner - the same guarantee this pattern already requires of every maintenance and errand script. |

No violations; Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: the data model (`Pattern`, `Finding`, `Allowlist
entry`, `ScanMode`, `HookInput`) and the four contracts introduce no additional abstractions
beyond the one script named in the Technical Context, and no new runtime dependency. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-commit-safety-gate/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: decisions D1-D10 + external control
├── data-model.md        # Phase 1: entities and state machine
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   └── cli-and-hooks.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
scripts/
├── scan_secrets.py      # new: the scanner (--staged/--paths/--history/--stdin-hook)
└── README.md            # updated: Maintenance row for scan_secrets.py

.githooks/
└── pre-commit            # new: POSIX sh, runs `python3 scripts/scan_secrets.py --staged`

.github/
└── workflows/
    └── secret-scan.yml   # new: push + pull_request, scan job + gitleaks job

.claude/
└── settings.json         # new: PreToolUse hook, Write|Edit|MultiEdit|NotebookEdit matcher

.scanignore                # new: seeded with the D3 fixture list

tests/
└── test_scan_secrets.py  # new: every pattern detect+allowlist proof, Luhn, masking, modes

CLAUDE.md                  # updated: Lesson 4 gate sentence names the scanner + hook activation
.specify/memory/constitution.md   # updated: 1.1.0 -> 1.2.0 (MINOR), Sync Impact Report
PATTERNS.md                 # updated: "Commit safety gate (v0.0.2)" entry
README.md                   # updated: Setup step (hooksPath) + "Public repo hygiene" section
Project_Structure.md        # updated: Director-layer rows + v0.0.2 Changelog row

headless/                   # UNCHANGED - scan_secrets.py deliberately does not depend on it
requirements.txt            # UNCHANGED - no new dependency
terraform/README.md         # UNCHANGED - no new cloud resource
Function_Mapping.md         # UNCHANGED - scan_secrets.py is a maintenance script, not an errand
```

**Structure Decision**: single project, same as v0.0.1. The scanner lands beside
`check_env.py` in `scripts/` as a second maintenance script, not inside `headless/`: it has no
relationship to browser sessions, secrets vaults, or preview artifacts, and keeping it
dependency-free from `headless/config.py` (which requires `python-dotenv`) is load-bearing for
the zero-install constraint (Technical Context, above).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None.
