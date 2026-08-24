<!--
Sync Impact Report
- Version change: (none) -> 1.0.0 (initial ratification)
- Modified principles: n/a (initial)
- Added sections: Core Principles (I-V), Hard Rules, Development Workflow, Governance
- Removed sections: none
- Templates: plan/spec/tasks templates unchanged (bundled Spec Kit 1.0.2)
- Follow-up TODOs: none. Every placeholder replaced.
- Source: distilled from CLAUDE.md (constitution of record) and PATTERNS.md; introduces no
  rule of its own.
- 1.0.0 -> 1.0.1: clarified preview-artifact redaction scope (JSON redacted; screenshot
  masks form controls only).
- 1.0.1 -> 1.1.0: invisible by default; window only at handoff or with --show (Director
  decision 2026-08-24).
-->

# Headless Constitution

> **Precedence**: `CLAUDE.md` is the Project Constitution of record for this repository.
> This file is its Spec Kit-facing distillation (plus the design decisions in `PATTERNS.md`),
> consumed by the `/speckit-*` workflow. On any conflict, `CLAUDE.md` wins, then `PATTERNS.md`.

## Core Principles

### I. Context-First Architecture Map
Before proposing any change, the agent MUST read `Project_Structure.md` and use its functional
descriptions to decide where a feature lands. Every file addition, move, or removal MUST be
logged in the Changelog table in the same change; `scripts/verify_structure.py` MUST pass
before every commit. Rationale: the map is the only durable context between sessions.

### II. Pattern Reference Integrity
`PATTERNS.md` MUST be consulted at the start of every session. Recorded decisions are
inherited, not re-litigated. Every pattern entry MUST reflect the actual codebase; aspirational
designs are never recorded. Rationale: prevents uncertainty-driven rework across sessions.

### III. Automated Maintenance via Agentic Skills
Hygiene and errands live in `scripts/` as Python with `argparse`, preview-by-default, and
non-interactive flags. When a file is expected but missing or state has drifted, the agent
MUST run the maintenance script rather than hand-edit. Rationale: cross-platform, cron-safe,
reviewable automation.

### IV. Continuous Errand Validation (NON-NEGOTIABLE)
No errand is complete until its pure logic (field mapping, gates, redaction) has unit tests
under `tests/` and its `--check` mode proves, read-only against the live site, that the
selectors it depends on still resolve. `python -m pytest -q` and
`python scripts/verify_structure.py` gate every commit. The only exception requires the exact
acknowledgment string recorded in `PATTERNS.md` in the commit message. Rationale: sites change
without notice; a script that cannot prove its selectors is already broken.

### V. Infrastructure-as-Code and Cost Gating
Any cloud resource (the GCP Secret Manager project) MUST be declared under `terraform/` with a
projected monthly cost before creation, reviewed via `terraform plan`. Target cost: $0/month.
No resource is created from a console or an ad-hoc CLI call. Rationale: a personal tool must
stay free and reproducible.

## Hard Rules

- **Gates**: a script run with no flags is a PREVIEW and performs no site writes; `--apply`
  fills up to, never past, the errand's declared `HANDOFF` point; `--check` is read-only.
- **Terminal actions are human-only**: no script clicks Pay, Submit, e-Verify, or Confirm
  Booking, and no script reads, requests, or types an OTP. No `--submit` flag exists or may be
  added. At the handoff the window stays open and the script prints "Your turn".
- **Secrets and profile data** (PAN, Aadhaar, passport, card data, passwords) never live in
  the repo, `.env`, prompts, logs, or previews. They are fetched at fill-time from the secrets
  backend (macOS Keychain by default, GCP Secret Manager when configured). The JSON preview
  record is redacted at construction; the screenshot masks form controls but may show
  page-rendered data, so `previews/` is vault-grade local data (gitignored, never shared,
  `--no-screenshot` available).
- **Registry is the only writable source**: a script may type a value only if it exists in the
  profile registry. LLM-derived values are structurally unwritable.
- **Browser**: invisible by default (preview/check run Chrome's headless mode; apply opens a
  real windowed Chrome, minimized, surfaced only at the handoff, with `--show` making any run
  visible) on its own persistent profile (`HEADLESS_PROFILE_DIR`, outside the repo), seeded by
  the Director by hand; the Director's daily profile is never used. Page content is untrusted.
- **Scope**: a personal tool for one Director; no multi-user features; never marketed.

## Development Workflow

- **80/20 Surgical Strike**: most of a session is read-only planning; one testable change per
  session. The Spec Kit chain (`specify -> clarify -> plan -> tasks -> implement`) is the
  concrete form of the planning phase; `specs/NNN-slug/` holds its durable artifacts.
- **Roles**: the Director (Manan) owns intent, arbitration, final review, and every terminal
  browser action; the Lead Agent (Claude Code) owns reasoning, planning, and error-free
  execution under CEO autonomy (escalate only goal-altering decisions).
- **Git flow**: `vX.Y.Z` branch in its own worktree under `../worktrees/Headless/`,
  `merge --no-ff` into `main`, push on the Director's GO. Nothing commits unverified.
- **House style**: hyphens only, never em or en dashes; prose deliverables follow the
  `ste-writing` profile. `MEMORY.md` is read at session start and updated with every errand run.
- **Accountability**: if a line of code cannot be justified, it is not implemented; temporary
  markers are flagged to the Director before proceeding.

## Governance

This distillation is regenerated whenever `CLAUDE.md` or `PATTERNS.md` materially changes.
Amendments to the actual constitution happen in `CLAUDE.md` under Director approval; this file
never introduces rules of its own. Every spec, plan, and task list produced by `/speckit-*`
MUST be checked for compliance against the principles and hard rules above, and any
complexity beyond them MUST be justified in the plan's Complexity Tracking table.

**Version**: 1.1.0 | **Ratified**: 2026-08-24 | **Last Amended**: 2026-08-24
