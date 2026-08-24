# Project Structure: Headless

Functional map of the codebase. Read this before proposing any change; log every file
addition, move, or removal in the Changelog table immediately (`scripts/verify_structure.py`
enforces it).

## Director Layer

| Path | Purpose |
| :--- | :--- |
| `CLAUDE.md` | **Constitution**: roles, the five core lessons (AVF-derived), and the Headless hard rules (gates, secrets, browser, working style). Wins on any conflict. |
| `PATTERNS.md` | **Pattern Registry**: established engineering patterns and design decisions. |
| `Project_Structure.md` | **Architecture Map**: this document, including the Changelog. |
| `Function_Mapping.md` | **Errand Map**: each errand script mapped to its site, reads, writes-up-to, secrets, and handoff point. |
| `MEMORY.md` | **Operating ledger**: identity and environment, known site traps, "Errands run" table, session ids, open items. Read at session start. |
| `README.md` | Setup and usage. |
| `LICENSE` | MIT. |
| `.gitignore` | Excludes secrets, the virtualenv, previews, and the Chrome profile. |
| `.env.example` | Template for the non-secret configuration in `.env`. |
| `requirements.txt` | Python dependencies (Playwright, python-dotenv, pytest). |
| `scripts/` | **Agentic Skills**: maintenance scripts and errand scripts (see `scripts/README.md`). |
| `terraform/` | **Infrastructure-as-Code**: the GCP Secret Manager project, cost-gated (README only until the project is created). |
| `.specify/` | **Spec Kit Core**: constitution distillation (`memory/constitution.md`), templates, Python and bash helper scripts, workflow registry. Mapped at directory level. |
| `.claude/` | **Claude Code Integration**: Spec Kit skills (`/speckit-*`) plus the framework-generic `prototype` and `skill-distill` skills inherited from AVF. Mapped at directory level. |
| `specs/` | **Feature Specs**: durable per-feature artifacts (`NNN-slug/spec.md`, `plan.md`, `tasks.md`, ...). Mapped at directory level. |

## Application Layer

| Path | Purpose |
| :--- | :--- |
| `headless/` | Reusable package: `config.py` (env and paths), `session.py` (headed persistent Chrome via Playwright or CDP attach), `secrets.py` (Keychain / GCP Secret Manager seam), `profile.py` (registry of typeable values), `gates.py` (preview / apply / check modes and the human handoff), `preview.py` (redacted screenshot + field-diff artifacts). *(Planned in spec 001; not yet on disk.)* |
| `scripts/check_env.py` | Environment self-test: Chrome, profile dir, Playwright, secrets backend. *(Planned in spec 001.)* |
| `scripts/probe.py` | First errand: open a URL in the Headless profile and write a preview artifact. *(Planned in spec 001.)* |
| `tests/` | `pytest` unit tests for pure logic. *(Planned in spec 001.)* |
| `previews/` | Redacted preview artifacts written at runtime. Gitignored; absent until first run. |

## Changelog

| Date | Action | Files Affected | Summary |
| :--- | :--- | :--- | :--- |
| 2026-08-24 | INITIALIZE | `CLAUDE.md`, `PATTERNS.md`, `Project_Structure.md`, `Function_Mapping.md`, `MEMORY.md`, `README.md`, `LICENSE`, `.gitignore`, `.env.example`, `requirements.txt`, `scripts/README.md`, `scripts/verify_structure.py`, `terraform/README.md` | **V0.0.0 Template Baseline.** Director layer materialized from Agentic-Vibe-Fleet (V0.0.7) for a Claude-led personal browser-errand runner: constitution of record is `CLAUDE.md` (five lessons adapted; Bruno gate replaced by errand validation), pattern registry seeded from the Director's Atlassian toolkit conventions (thin package, one script per errand, preview-by-default, registry-only writes). GitHub Spec Kit 1.0.2 initialized with the Claude integration and Python scripts; constitution distillation seeded from this repo's own `CLAUDE.md`. AVF's Gemini-only LLM scripts, `.gemini/`, and `bruno/` deliberately not carried over. `verify_structure.py` exclusions extended for `.venv/`, `previews/`, `tests` caches. Cost review: $0, no infra. |
