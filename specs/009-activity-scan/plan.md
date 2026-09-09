# Implementation Plan: Activity Scan

**Branch**: `v0.0.9` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-activity-scan/spec.md`

## Summary

Add one read-only errand, `scripts/activity_scan.py`, and its pure logic module,
`headless/activities.py`, that rank public venues around a point for an evening out. The errand
searches the Google Maps list view under headless Chrome, folds duplicates, excludes movies and
dinner, scores by a Bayesian-shrunk rating and distance, checks each top venue's own hours
against the Director's evening window, and writes a Markdown and a JSON report. There is no
apply mode. Decisions are recorded in [research.md](research.md) (D1-D13).

## Technical Context

**Language/Version**: Python 3.14 (this worktree's own `.venv`, unchanged from every prior
feature).

**Primary Dependencies**: none new. `headless/session.py` (Playwright), `headless/gates.py`
(`Mode.PREVIEW`), `headless/capture.py`'s `reports_dir_for` - all already present.
`headless/activities.py` and `scripts/activity_scan.py` are the only new files.

**Storage**: `reports/activity/activity-scan-<UTC date>.md` and `.json` - a new sibling directory
to `reports/captures/` and `reports/policy/`, resolved from `config.preview_dir`'s own sibling
exactly as those two already are. No new environment variable, no new CLI flag on any other
script.

**Testing**: `pytest>=8` (already a dependency). Every path is exercised through a stubbed
`Session` and stubbed browser-reading functions (`FakeSession`, `FakePage`) - never a real
browser, never a real network call, per NFR-001.

**Target Platform**: macOS (this Director's own machine), unchanged from every prior feature.

**Project Type**: package + errand addition (`headless/activities.py`, `scripts/activity_scan.py`
new; no existing file modified).

**Performance Goals**: not latency-sensitive. The feed scroll caps at 8 attempts; detail
enrichment caps at `--details` (default 60) place-page visits.

**Constraints**: no `--apply` mode exists, and none may be added (the module docstring and
`HANDOFF` both state this). No secret, vault item, or profile field is read or written. The point
(`--near`) is a command-line argument only, never persisted to the repository.

**Scale/Scope**: one Director, one scan per invocation, no concurrency, no scheduling.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / Hard Rule | Status | Notes |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | Pass | `Project_Structure.md` gains updated `headless/`/`reports/` row text, a new `scripts/activity_scan.py` row, and one new Changelog row - applied in this same delivery |
| II. Pattern Reference Integrity | Pass | `PATTERNS.md` gains one new entry recording the selector choice, the read-only posture, and the recon findings - applied in this same delivery |
| III. Automated Maintenance via Agentic Skills | Pass | One new errand script, `argparse`-driven, preview-by-default (in fact preview-only) |
| IV. Continuous Errand Validation | Pass | 140 unit tests already ship with the code; `--check` is the live selector probe this hard rule requires |
| V. Infrastructure-as-Code and Cost Gating | Pass, trivially | No cloud resource; Nominatim is a free, unauthenticated public service, called at most once per run |
| **Terminal Actions hard rule** ("no script clicks Pay, Submit...") | Unaffected | This errand never clicks, fills, or submits anything - it only reads |
| **Secrets hard rule** ("secrets never live in... prompts... logs") | Unaffected | This errand touches no secret and no vault item |

No amendment is drafted for this feature; the Complexity Tracking table below is empty for the
same reason.

## Project Structure

### Documentation (this feature)

```text
specs/009-activity-scan/
├── plan.md              # This file
├── research.md          # D1-D13, evidence from the 2026-09-09 recon
├── data-model.md         # Venue fields, report file shapes, the pipeline state flow
├── contracts/
│   └── scan-and-report.md   # Normative CLI contract and report file contract
├── quickstart.md          # Check mode, a lat/lon scan, an address scan, a custom queries file,
│                           # reading the report
├── tasks.md               # As-built task breakdown, grouped by user story
└── checklists/
    └── requirements.md    # Specification quality checklist
```

### Source code (repository root)

```text
headless/
└── activities.py         # NEW: parsers, geography, day-window verdict, score, duplicate
                           # folding, rank, markdown/json renderers, DEFAULT_QUERIES, selector
                           # constants

scripts/
└── activity_scan.py       # NEW: the read-only errand - argparse, --check probe, the scan
                            # pipeline, the always-refused hidden --apply flag

tests/
├── test_activities.py     # NEW: unit tests for headless/activities.py
└── test_activity_scan.py  # NEW: unit tests for scripts/activity_scan.py (FakeSession, stubbed
                            # read_search_page/read_place_page)

PATTERNS.md, Project_Structure.md, scripts/README.md, Function_Mapping.md, MEMORY.md
                                                                # MODIFIED: docs of record
```

**Structure Decision**: single project, same layout every prior feature in this repository uses.
No new top-level directory beyond `reports/activity/`, which is a sibling under the existing
gitignored `reports/` tree.

## Complexity Tracking

*No entry.* This feature adds one new errand and one new pure-logic module inside the existing
package layout; it records no constitutional deviation.
