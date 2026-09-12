# Implementation Plan: Product Scan

**Branch**: `v0.0.11` | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-product-scan/spec.md`

## Summary

Add one read-only errand, `scripts/product_scan.py`, and its pure logic module,
`headless/products.py`, that rank public retail listings for a product query and state where a
Director-supplied reference listing (a listing the Director was sent, or any other) would rank
against them. The errand searches Amazon by default and Home Depot as an opt-in second source, folds
duplicate listings by their canonical URL, parses each title's height, length, material, stakes,
and no-dig flag, scores every kept listing, groups the scored listings into three material tiers,
and writes a Markdown and a JSON report. There is no apply mode. Decisions are recorded in
[research.md](research.md) (D1-D10).

## Technical Context

**Language/Version**: Python 3.14 (this worktree's own `.venv`, unchanged from every prior
feature).

**Primary Dependencies**: none new. `headless/session.py` (Playwright), `headless/gates.py`
(`Mode.PREVIEW`), `headless/capture.py`'s `reports_dir_for` - all already present.
`headless/products.py` and `scripts/product_scan.py` are the only new files.

**Storage**: `reports/product/product-scan-<slug>-<UTC date>.md` and `.json` (fix batch A5/B9,
2026-09-11: the query's own slug precedes the date) - a new sibling directory to
`reports/activity/`, `reports/captures/`, and `reports/policy/`, resolved from
`config.preview_dir`'s own sibling exactly as those three already are. No new environment
variable, no new CLI flag on any other script.

**Testing**: `pytest>=8` (already a dependency). Every path is exercised through a stubbed
`Session` and stubbed browser-reading functions (`FakeSession`, `FakePage`, modeled on
`tests/test_activity_scan.py`'s own fakes) - never a real browser, never a real network call, per
NFR-001.

**Target Platform**: macOS (this Director's own machine), unchanged from every prior feature.

**Project Type**: package + errand addition (`headless/products.py`, `scripts/product_scan.py`
new; no existing file modified).

**Performance Goals**: not latency-sensitive. Search reads cap at `--pages` (default 2, max 5)
pages per selected site; Home Depot's own lazy-load scroll caps at 6 attempts; the reference read
is at most one page visit.

**Constraints**: no `--apply` mode exists, and none may be added (the module docstring and
`HANDOFF` both state this). No secret, vault item, or profile field is read or written. The query
(`--query`) and the reference (`--reference-url`/`--reference`) are command-line arguments only,
never persisted to the repository.

**Scale/Scope**: one Director, one product query per invocation, no concurrency, no scheduling.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / Hard Rule | Status | Notes |
| :--- | :--- | :--- |
| I. Context-First Architecture Map | Pass | `Project_Structure.md` gains updated `headless/`/`reports/` row text, a new `scripts/product_scan.py` row, and one new Changelog row - applied by the implementation builder in this same delivery |
| II. Pattern Reference Integrity | Pass | `PATTERNS.md` gains one new entry recording the ranking rule, the site-tiering decision (Amazon primary, Home Depot opt-in, Walmart reference-only), and the recon findings - applied by the implementation builder in this same delivery |
| III. Automated Maintenance via Agentic Skills | Pass | One new errand script, `argparse`-driven, read-only (never even preview-then-apply - there is no apply mode at all) |
| IV. Continuous Errand Validation | Pass | Unit tests cover every parser and the scoring/ranking/folding logic; `--check` is the live selector probe this hard rule requires, covering both selected sites |
| V. Infrastructure-as-Code and Cost Gating | Pass, trivially | No cloud resource; every site read is a free, unauthenticated public page |
| **Terminal Actions hard rule** ("no script clicks Pay, Submit...") | Unaffected | This errand never clicks, fills, or submits anything - it only reads |
| **Secrets hard rule** ("secrets never live in... prompts... logs") | Unaffected | This errand touches no secret and no vault item |

No amendment is drafted for this feature; the Complexity Tracking table below is empty for the
same reason.

## Project Structure

### Documentation (this feature)

```text
specs/011-product-scan/
├── plan.md                # This file
├── research.md            # D1-D10, evidence from the 2026-09-11 recon
├── data-model.md          # Listing fields, report file shapes, the pipeline state flow
├── contracts/
│   └── scan-and-report.md # Normative CLI contract and report file contract
├── quickstart.md          # Check mode, an Amazon-only scan, a Home Depot opt-in scan, a
│                           # reference-URL scan, a hand-typed reference, reading the report
├── tasks.md                # Delivery-plan task breakdown, grouped by user story
└── checklists/
    └── requirements.md     # Specification quality checklist
```

### Source code (repository root)

```text
headless/
└── products.py             # NEW: selector constants, parsers (price, rating, count,
                             # attributes), price-per-foot, scoring, tiering, ranking,
                             # duplicate folding, the reference-literal parser, and the
                             # markdown/json renderers

scripts/
└── product_scan.py         # NEW: the read-only errand - argparse, --check probe, the
                             # search-fold-score-tier-rank-reference-render pipeline, the
                             # always-refused hidden --apply flag

tests/
├── test_products.py        # NEW: unit tests for headless/products.py
└── test_product_scan.py    # NEW: unit tests for scripts/product_scan.py (FakeSession,
                             # FakePage, stubbed read_amazon_search/read_homedepot_search/
                             # read_amazon_product/read_walmart_product)

PATTERNS.md, Project_Structure.md, scripts/README.md, Function_Mapping.md, MEMORY.md
                                                                # MODIFIED: docs of record
                                                                # (implementation builder only)
```

**Structure Decision**: single project, same layout every prior feature in this repository uses.
No new top-level directory beyond `reports/product/`, which is a sibling under the existing
gitignored `reports/` tree.

## Complexity Tracking

*No entry.* This feature adds one new errand and one new pure-logic module inside the existing
package layout; it records no constitutional deviation.
