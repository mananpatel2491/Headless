# Implementation Plan: Foundation Errand Runner

**Branch**: `v0.0.1` | **Date**: 2026-08-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-foundation-errand-runner/spec.md`

## Summary

Deliver the shared mechanics every Headless errand composes: a `headless/` package with
configuration, a headed persistent-profile Chrome session (Playwright, installed Chrome
channel, optional CDP attach), a vault seam (macOS Keychain default, GCP Secret Manager
selectable), a profile registry as the only typeable source, preview/apply/check gates with
a human handoff, and redacted preview artifacts. Ship two errands on top: `check_env` (four
row self-test) and `probe` (open a URL, seed logins, write a preview). Prove it with a
browser-free unit suite plus a fixture-page browser suite (opt-in) and wire both into the
commit gate. Decisions are recorded in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.14 (venv per worktree)

**Primary Dependencies**: `playwright>=1.62` (installed Chrome via `channel="chrome"`),
`python-dotenv>=1.0`; optional `google-cloud-secret-manager` in `requirements-gcp.txt`

**Storage**: macOS Keychain items (secrets and the `profile` JSON document); Chrome profile
directory under `~/.headless/`; preview artifacts under `previews/` (gitignored). No database.

**Testing**: `pytest>=8`; unit suite without a browser; integration module on a local
fixture page, opt-in via `HEADLESS_TEST_BROWSER=1`

**Target Platform**: macOS (Director's machine); code stays cross-platform where free but
the Keychain backend and `check_env` hints are macOS-specific in this feature

**Project Type**: CLI scripts over a small library (single project)

**Performance Goals**: `check_env` under 30 s (SC-004); unit suite under 10 s (SC-005);
config failure under 2 s with no window (SC-006)

**Constraints**: no secret or registry value in stdout, logs, or artifacts (FR-010); no
submit/pay/verify/OTP path anywhere (FR-007); apply only with a human at a TTY and a visible
browser (FR-008); $0 cloud cost (constitution Lesson 5)

**Scale/Scope**: one user, one machine; 7 package modules, 2 errand scripts, 1 fixture page,
~8 test modules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / rule | Status | Evidence |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | PASS | `Project_Structure.md` already maps the planned `headless/`, `scripts/check_env.py`, `scripts/probe.py`, `tests/`, `previews/`; the implementation commit logs every file in the Changelog. |
| II. Pattern Reference Integrity | PASS | Design follows the registered patterns (thin package, one script per errand, preview-by-default, registry-only writes, secrets seam, persistent headed profile, redact-before-write). New facts learned during implementation are appended to `PATTERNS.md`, none aspirational. |
| III. Automated Maintenance via Agentic Skills | PASS | Both errands are Python `argparse` scripts with non-interactive flags; `verify_structure.py` stays in the gate. |
| IV. Continuous Errand Validation | PASS | Unit tests for config, gates, redaction, registry, vault, preview; `--check` implemented in the base `Errand`; commit gate = `pytest` + `verify_structure.py`. |
| V. IaC and Cost Gating | PASS | No cloud resource is created in this feature; the GCP backend is code-only and its future project is described with a $0 projection in `terraform/README.md`. |
| Gates hard rule | PASS | `Mode` has three values; `resolve_mode` refuses apply without TTY or headed; no submit flag or helper exists (contract lists the forbidden flags and a test asserts the parser rejects them). |
| Secrets hard rule | PASS | Vault seam; `.env` documented as non-secret; `PreviewRecord` masks at construction; `Session.fill` accepts only `FieldPlan`. |
| Browser hard rule | PASS | Dedicated persistent profile outside the repo; invisible by default (headless for preview/check, quiet window for apply, `--show` to watch); CDP attach optional. |
| Spec-driven workflow | PASS | This feature runs specify -> plan -> tasks -> implement on `v0.0.1` in a worktree. |

No violations; Complexity Tracking is empty.

**Post-design re-check (after Phase 1)**: the data model and contracts introduce no
additional abstractions beyond the seven modules named in the Technical Context. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation-errand-runner/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0: decisions D1-D10
├── data-model.md        # Phase 1: entities and state machine
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   └── cli-and-package.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
headless/
├── __init__.py          # package docstring, version
├── config.py            # Config dataclass, load_config, ConfigError
├── gates.py             # Mode, GateRefused, add_mode_arguments, resolve_mode
├── secrets.py           # VaultBackend protocol, KeychainBackend, GcpBackend, open_vault
├── profile.py           # ProfileRegistry, RegistryMissing
├── fields.py            # FieldPlan, Source, parse_source, redact
├── preview.py           # PreviewRecord, write_artifacts
├── session.py           # Session (launch / attach, goto, probe, fill, screenshot, handoff)
└── errand.py            # Errand base class: argparse wiring + the run state machine

scripts/
├── README.md            # inventory updated with the two errands
├── verify_structure.py  # existing
├── check_env.py         # errand: environment self-test
└── probe.py             # errand: open a URL in the Headless profile

tests/
├── conftest.py          # FakeVault, fixture paths, tmp preview dir
├── fixtures/form.html   # local form with text inputs, a select, and a submit control that records clicks
├── test_config.py
├── test_gates.py
├── test_fields.py       # parse_source + redact
├── test_secrets.py      # FakeVault, KeychainBackend command shape, GcpBackend with fake client, open_vault
├── test_profile.py
├── test_preview.py      # masking invariant + artifact naming
├── test_errand.py       # run() state machine with a stubbed Session
└── test_gates_browser.py  # opt-in: preview / check / stubbed apply on fixtures/form.html

requirements.txt         # + nothing new (playwright, python-dotenv, pytest already listed)
requirements-gcp.txt     # google-cloud-secret-manager (optional extra)
.env.example             # existing keys; unchanged
Function_Mapping.md      # rows for check_env and probe
Project_Structure.md     # Changelog row for v0.0.1
PATTERNS.md              # append facts learned (only if any)
MEMORY.md                # Errands run rows for the quickstart runs
```

**Structure Decision**: single project. The package name is `headless`, scripts import it
via `sys.path` insertion of the repo root (same convention as the Director's Atlassian
toolkit) so no packaging step is needed for a personal tool.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

None.
