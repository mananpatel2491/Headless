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
- 1.1.0 -> 1.2.0 (MINOR: a new hard rule added, no principle removed or redefined): the
  commit safety gate (specs/002-commit-safety-gate). The repository went public
  2026-08-24; every commit is now scanned for credentials and personal identifiers at
  three points (a local git pre-commit hook, a Claude Code write-time check, a CI
  backstop that also runs GitHub's own secret scanning and push protection). Principle IV
  and the Continuous Errand Validation hard rule now name `scripts/scan_secrets.py
  --staged` alongside `pytest`/`verify_structure.py`; a new Hard Rules bullet,
  "Public repository hygiene", records the gate and its one-time per-clone activation
  step (git never runs a tracked hook file on its own). Templates unchanged.
- 1.2.0 -> 1.2.1 (PATCH: wording only, no principle or hard rule added, removed, or
  redefined): login persistence (specs/003-login-persistence). A seeded login now
  survives to the next run: on the launched-profile path only, the profile directory
  also holds a plaintext session-cookie state file (`session-cookies.json`), and every
  Chrome launch in the codebase now passes the sandbox-on launch option. The Secrets and
  Browser Hard Rules bullets each gain one sentence naming this file and its vault-grade
  classification and recording that the CDP-attach path never touches it; this extends
  the reach of the existing "secrets never live in ... previews or logs" and "the
  Director's daily Chrome profile is never used" rules to one more file inside a
  directory those rules already govern, rather than stating a new rule. Templates
  unchanged.
- 1.2.1 -> 1.3.0 (MINOR: the default secrets backend changed, and one new explicit hard
  rule is added - not a wording-only PATCH, unlike 1.2.1's own bump): the local age vault
  (specs/004-age-vault). The Director replaced the planned GCP Secret Manager plus PAM
  approval backend with a local, open-source, passphrase-encrypted vault (`age`); the
  default value of `HEADLESS_SECRETS_BACKEND` changes from `keychain` to `age` (both
  `KeychainBackend` and `GcpBackend` remain in place and selectable, unmodified). The
  Secrets Hard Rules bullet is rewritten to name the vault, its per-run passphrase gate
  (no caching of any kind - the passphrase never enters Python), and a new explicit rule:
  no backend ever stores a password or a payment card value. `terraform/README.md`
  records the GCP Secret Manager plan as superseded, not deleted. Templates unchanged.
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
selectors it depends on still resolve. `python -m pytest -q`,
`python scripts/verify_structure.py`, and `python scripts/scan_secrets.py --staged` (the
commit safety gate) gate every commit. The only exception requires the exact acknowledgment
string recorded in `PATTERNS.md` in the commit message. Rationale: sites change without
notice; a script that cannot prove its selectors is already broken - and, since the
repository is public, a commit that cannot prove it carries no credential or personal
identifier is a public exposure, not a private one.

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
  backend: a local, passphrase-encrypted `age` vault by default (specs/004-age-vault;
  `HEADLESS_AGE_FILE`, default `~/.headless/profile.age`, written only by `scripts/vault.py`),
  the macOS Keychain, or GCP Secret Manager when explicitly selected. The vault's passphrase
  is the approval gate: every run touching a `secret:`/`registry:` field plan source prompts
  for it on that run's own controlling terminal, every time - no caching of any kind, and no
  code path in `headless/` or `scripts/` ever reads, stores, or logs it. No backend ever
  stores a password or a payment card value; a login persists through the session-cookie
  mechanism below instead. The JSON preview record is redacted at construction; the
  screenshot masks form controls but may show page-rendered data, so `previews/` is
  vault-grade local data (gitignored, never shared, `--no-screenshot` available). The profile
  directory's own session-cookie file (`session-cookies.json`, launched-profile path only)
  inherits this same vault-grade classification; a cookie name or value never appears in a
  note, an exception message, or any preview artifact.
- **Registry is the only writable source**: a script may type a value only if it exists in the
  profile registry. LLM-derived values are structurally unwritable.
- **Browser**: invisible by default (preview/check run Chrome's headless mode; apply opens a
  real windowed Chrome, minimized, surfaced only at the handoff, with `--show` making any run
  visible) on its own persistent profile (`HEADLESS_PROFILE_DIR`, outside the repo), seeded by
  the Director by hand; the Director's daily profile is never used. Page content is untrusted.
  The profile directory also holds a plaintext session-cookie file that lets a seeded login
  persist across runs; the CDP-attach path never reads or writes it.
- **Scope**: a personal tool for one Director; no multi-user features; never marketed.
- **Public repository hygiene** (specs/002-commit-safety-gate): the repository is public.
  Every commit is scanned for credentials and personal identifiers before it is created
  (`.githooks/pre-commit`, `git config core.hooksPath .githooks` - a one-time, per-clone
  step `scripts/check_env.py`'s `git_hooks` row verifies is active); every write an
  assistant makes to a file in this repository is scanned before it reaches disk
  (`.claude/settings.json`'s `PreToolUse` hook); every pushed change is scanned again in CI
  across its full history, alongside GitHub's own secret scanning and push protection. A
  known-safe value is exempted via `.scanignore` or an inline `# scan:allow` marker, never
  by weakening a detection pattern.

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

**Version**: 1.3.0 | **Ratified**: 2026-08-24 | **Last Amended**: 2026-08-25
