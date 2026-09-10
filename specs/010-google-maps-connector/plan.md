# Implementation Plan: Google Maps Connector

**Branch**: `v0.0.10` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

## Summary

Register Google's own hosted Maps Grounding Lite MCP server (`https://mapstools.googleapis.com/mcp`)
project-wide via `.mcp.json`, so a future Claude Code session in this repository can identify a
location, geocode a name, compute a route, or read the weather without a browser. Add the pure
JSON-RPC message-shape module (`headless/mapsmcp.py`) and the Lesson 4 live check
(`scripts/maps_check.py`) that proves the handshake, the tool listing, and (when a key is
present) one billable `search_places` call all work, printing value-free PASS/FAIL/SKIP rows.
Declare the one cloud resource the connector needs - a restricted API key - under `terraform/`,
cost-gated per Lesson 5, applied only by the Director. The key lives in the macOS Keychain and
the Director's login shell, never the age vault (an MCP server has no controlling terminal for
`age` to prompt on) and never a file in this repository. Decisions are recorded in
[research.md](research.md) (D1-D7).

## Technical Context

**Language/Version**: Python 3.14 (this worktree's own `.venv`), standard library only
(`urllib.request`, `json`, `dataclasses`) - no new dependency in `requirements.txt`.

**Primary Dependencies**: none new for the Python side. `terraform/` adds the `hashicorp/google`
provider (`~> 6.0`), declared only in `terraform/main.tf`'s own `required_providers` block - not
a Python dependency, and not installed by `pip`.

**Storage**: none. `.mcp.json` is a static, committed configuration file (no secret value in it);
`terraform/.terraform.lock.hcl` is committed; `terraform/.terraform/`, state, and `*.tfvars` stay
gitignored. No report, preview, or cache file is written by either new Python module.

**Testing**: `pytest>=8` (already a dependency). `tests/test_maps_check.py` stubs
`urllib.request.urlopen` via `monkeypatch` - zero real network calls, zero real key, matching
this repository's existing browser-free testing convention (`FakeSession`/`FakePage` for
`activity_scan.py`, an injectable `fetch` for its Nominatim call).

**Target Platform**: macOS (this Director's own machine), unchanged from every prior feature. The
Keychain step in quickstart.md Scenario 2 is macOS-specific; a Windows session would use its own
Credential Manager equivalent and set the same environment variable, per this repository's
existing cross-platform secrets-backend precedent.

**Project Type**: package + maintenance-script addition (`headless/mapsmcp.py`,
`scripts/maps_check.py`, `.mcp.json`, `terraform/*.tf` new; no existing `.py` file modified).

**Performance Goals**: not latency-sensitive. `maps_check.py` makes at most four JSON-RPC round
trips (`initialize`, `notifications/initialized`, `tools/list`, at most one `tools/call`), each
under the script's own 30-second timeout.

**Constraints**: no browser is ever opened by this feature. The key is read from the environment
only, never a file, never the vault. `--no-search` must never make a billable call. No resource
under `terraform/` is created by anyone but the Director, and never from the console or an
ad-hoc CLI call.

**Scale/Scope**: one Director, occasional interactive tool calls plus one live-check run per
verification; no scheduling, no concurrency.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / Hard Rule | Status | Notes |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | Pass | `Project_Structure.md` gains an extended `headless/` row, new rows for `scripts/maps_check.py`, `.mcp.json`, and `terraform/`, an extended `tests/` row, and one new Changelog row - applied in this same delivery |
| II. Pattern Reference Integrity | Pass | `PATTERNS.md` gains one new entry recording the connector choice, the cost gate, and the no-vault reasoning - applied in this same delivery |
| III. Automated Maintenance via Agentic Skills | Pass | `scripts/maps_check.py` is a maintenance script (`argparse`, no preview/apply/check modes, no `HANDOFF`), matching `check_env.py`'s own precedent |
| IV. Continuous Errand Validation | Pass | 25 unit tests ship with the code, plus a live handshake proof against the real endpoint (2026-09-09, no key) recorded in MEMORY.md; `maps_check.py` is itself the Lesson 4 live check for this dependency |
| V. Infrastructure-as-Code and Cost Gating | Pass | `terraform/` declares the ONLY cloud resources this feature needs, with a projected $0/month cost table at personal volume (see terraform/README.md); no resource is created by this delivery itself |
| **Terminal Actions hard rule** ("no script clicks Pay, Submit...") | Unaffected | This feature opens no browser at all - there is no terminal action to reach |
| **Secrets hard rule** ("secrets never live in... prompts... logs") | Pass, with a documented exception to the vault default | The key never lives in the repository, `.env` (beyond the placeholder), a log, or a preview; it deliberately does not live in the `age` vault either (research.md D3) - the Keychain plus a login-shell export is the recommended home instead |

No amendment is drafted for this feature; the Complexity Tracking table below is empty for the
same reason.

## Project Structure

### Documentation (this feature)

```text
specs/010-google-maps-connector/
├── plan.md                        # This file
├── research.md                    # D1-D7, the connector's own design decisions
├── data-model.md                   # JSON-RPC message shapes, CheckOutcome, the terraform resources
├── contracts/
│   └── connector-and-check.md      # .mcp.json contract, the check's CLI contract, terraform I/O
├── quickstart.md                   # Apply terraform, store the key, run the check, approve the
│                                    # server, rotate/revoke
├── tasks.md                        # As-built task breakdown, grouped by user story
└── checklists/
    └── requirements.md             # Specification quality checklist
```

### Source code (repository root)

```text
.mcp.json                          # NEW: project-scoped registration of the google-maps server

headless/
└── mapsmcp.py                     # NEW: JSON-RPC message builders/readers, CheckOutcome - pure,
                                    # no network I/O

scripts/
└── maps_check.py                  # NEW: the Lesson 4 live check - Transport, run_check, main;
                                    # a maintenance script, not a browser errand

tests/
└── test_maps_check.py             # NEW: 25 tests, urllib.request.urlopen stubbed - message
                                    # shapes, both body shapes, the transport, the CLI exit codes

terraform/
├── main.tf                        # NEW: the two service enablements and the restricted key
├── variables.tf                   # NEW: var.project_id
├── outputs.tf                     # NEW: maps_api_key (sensitive), mcp_endpoint
├── .terraform.lock.hcl            # NEW: committed provider dependency lock
└── README.md                      # REWRITTEN: superseded Secret Manager history kept short,
                                    # then this feature's own cost gate and apply steps

PATTERNS.md, Project_Structure.md, scripts/README.md, Function_Mapping.md, README.md,
.env.example, .gitignore, MEMORY.md
                                                                # MODIFIED: docs of record
                                                                # (.env.example and .gitignore
                                                                # already carry this feature's
                                                                # own note/block; not edited by
                                                                # this delivery's own document
                                                                # pass)
```

**Structure Decision**: single project, same layout every prior feature in this repository uses.
`terraform/` already existed as a placeholder directory (README only, spec-less, superseded
Secret Manager plan); this is the first feature to populate it with real declarations.

## Complexity Tracking

*No entry.* This feature adds one pure-logic module, one maintenance script, one static
configuration file, and one small Terraform declaration; it records no constitutional deviation.
