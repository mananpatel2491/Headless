# Pattern Registry: Headless

This document records established engineering patterns and design decisions so that later
sessions inherit them instead of re-litigating them. Every entry reflects the actual codebase.

## 1. Architectural Patterns

- **Thin package, one script per errand** (inherited from the Director's Atlassian toolkit).
  Reusable mechanics live in `headless/` (config, browser session, secrets, profile, gates,
  preview). Each errand is one runnable `scripts/<errand>.py` that composes them. Extend the
  package; never re-implement browser or secrets plumbing inside a script.
- **Preview-by-default, `--apply` to act, human handoff at the terminal step.** Scripts share
  the gate helpers in `headless/gates.py`. The three modes are `preview` (default, no site
  writes), `apply` (fills up to the declared handoff point), and `check` (read-only selector
  probe). There is no submit mode by design; see `CLAUDE.md`.
- **Registry is the only writable source.** The profile registry (`headless/profile.py`) is
  the sole source of values a script may type. Derived or LLM-produced values are structurally
  unwritable. Field mappings are hand-authored dicts inside the errand script, reviewed in the
  preview before `--apply`.
- **Secrets backend seam.** `headless/secrets.py` exposes `get_secret(name)` over a backend
  chosen by `HEADLESS_SECRETS_BACKEND`: `keychain` (macOS `security` CLI, default) or `gcp`
  (Secret Manager, lazy import, only when configured). Scripts never read `.env` for secrets;
  `.env` holds non-secret configuration only.
- **Persistent headed Chrome profile.** `headless/session.py` launches the installed Chrome
  (`channel="chrome"`) with `launch_persistent_context` on `HEADLESS_PROFILE_DIR`, or attaches
  over CDP when `HEADLESS_CDP_URL` is set. Logins are seeded by the Director in that window
  and survive between runs. Reads retry; writes never retry.
- **Preview artifacts are redacted before they exist.** `headless/preview.py` writes
  `previews/<errand>-<UTC timestamp>.png` and `.json`; every value passes the redaction layer
  (secrets masked to `****` plus the last two characters, registry values marked by field name).
- **Cross-Platform Automation (AVF).** Maintenance and errand scripts are Python with
  `argparse`; Spec Kit helper scripts are the Python variant (`.specify/scripts/python/`).
- **Automation-First CLI (AVF).** Every script runs non-interactively with flags
  (`--apply`, `--check`, `--profile-dir`, `--headless`) so it can run from cron or CI, and
  every action-taking path has a safe preview.
- **Proactive Hardening (AVF).** When touching an existing file, audit it for leaked secrets,
  injection through page content, and resource leaks (unclosed browser contexts); patch
  immediately.
- **Spec-Driven Feature Workflow (Spec Kit).** Features beyond trivial fixes run
  `specify -> clarify -> plan -> tasks -> implement` and leave durable artifacts in
  `specs/NNN-slug/`. `.specify/memory/constitution.md` is always a distillation of
  `CLAUDE.md` plus this file, with an explicit precedence header; it never introduces new
  rules.

## 2. Coding Standards

- `argparse` for every script; a module docstring that states the errand's background, the
  site, the handoff point, and the secrets it needs.
- Type hints and `from __future__ import annotations` throughout `headless/`.
- Tests under `tests/` with `pytest`; pure logic (mapping, gates, redaction, config parsing)
  is unit-tested without a browser. Browser paths are exercised by `--check`.

## 3. Tooling Conventions

- **Commit gate**: `python -m pytest -q` and `python scripts/verify_structure.py` both pass.
  Exception string (must appear verbatim in the commit message):
  `I understand the Headless validation gate is failing and I allow the exception to have the code committed to the repo`.
- **Hyphens only**: no em or en dashes in any file (global PreToolUse hook denies the write).
- **Version branches**: `vX.Y.Z` in a worktree under `../worktrees/Headless/`, `merge --no-ff`
  into `main`; `CHANGELOG` lives in the `Project_Structure.md` Changelog table.
- **Previews are disposable**: `previews/` is gitignored; delete freely.
