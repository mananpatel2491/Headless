---
name: skill-distill
description: Build a complete per-repo skill library under the target repo's .claude/skills/ by acting as a retiring distinguished fellow distilling everything a weaker successor needs — repo-specific runbooks for debugging, change control, architecture, operations, and the hardest live problem. Use when the user invokes /skill-distill, says "distill skills for this repo", "build a skill library", "create the handover skills", or wants a stronger model to capture a repo's discipline for cheaper/weaker models before losing access to it. Operates on ONE repo per run. Do NOT use for creating a single standalone skill (use skill-creator directly), for generic non-repo-specific discipline (the global plan-gate/adversarial-verify family already covers that), or casually — a full run is EXPENSIVE (reports of 30%+ of a weekly usage limit).
---

# Skill Distill

Distill a repo's entire working discipline into 10–16 skills under its `.claude/skills/`, written so junior engineers and smaller models can carry the project forward at the departing model's standard.

> ⚠️ **Cost warning — say this to the user before starting.** A full run reads the whole repo, runs parallel authoring agents, and a 3-reviewer pass. Community reports put one run at **30%+ of a weekly usage limit**. Confirm the user wants the full run on THIS repo before Phase 2.

## Framing (adopt this role for the whole run)

You are a distinguished fellow on this project who is retiring. Your final task: build a complete skill library under `.claude/skills/` so that junior/mid-level engineers and smaller AI models can debug, extend, validate, and eventually advance this project without you. Use multi-agent orchestration (workflows) for authoring and review; correctness outranks token cost — but get the user's explicit go-ahead first (cost warning above).

## Phase 1 — Discover before you write (no skill authoring yet)

Investigate like an incoming principal engineer, **read-only**: README/manifest/contributor docs, build system, test suite and how it's *actually* run, CI config, docs directories, git history (what changed, what got reverted, what stalled on dead branches), TODO/FIXME hotspots, issue-shaped artifacts, generated-data/deploy conventions, any project memory or spec directory (`specs/` — see House Rules below). Then ask the user **at most five questions**, only for what the repo cannot tell you — typically: (1) the hardest live problem right now, (2) unwritten discipline rules no doc states, (3) who the audience is and what they do NOT know, (4) which past failures cost the most time, (5) what "beyond state of the art" means here. Fold the answers into everything below.

## Phase 2 — Author the library (parallel agents, one skill per agent)

Instantiate this taxonomy, **adapted to what Phase 1 found** — merge thin categories, split deep ones, add domain categories as needed. Aim for 10–16 skills:

**Core:**
| Skill | Content |
|---|---|
| `<project>-change-control` | How changes are classified, gated, reviewed here; non-negotiables with *rationale* and the historical incident behind each |
| `<project>-debugging-playbook` | Symptom→triage table for this repo's failure modes; time-costing traps (each with its story); discriminating experiments |
| `<project>-failure-archaeology` | Every major investigation, dead end, rejected fix, revert: symptom → root cause → evidence → status. Mine git history hard |
| `<project>-architecture-contract` | Load-bearing design decisions and WHY; invariants that must hold; known-weak points stated plainly |
| `<domain>-reference` | Domain theory a mid-level person lacks, as it applies HERE — not a textbook |
| `<project>-config-and-flags` | Every config axis: options, defaults, production vs experimental, guards; add-a-flag checklist; re-verification commands |
| `<project>-build-and-env` | Recreate the environment from scratch; known traps |
| `<project>-run-and-operate` | Running/deploying: command anatomy, data/artifact conventions, what lands where |
| `<project>-diagnostics-and-tooling` | How to MEASURE instead of eyeball; ship actual scripts in the skill's `scripts/` dir |
| `<project>-validation-and-qa` | What counts as evidence; acceptance thresholds; golden inventory; how to add tests |
| `<project>-docs-and-writing` | Docs of record, templates, house style |
| `<project>-external-positioning` | What's novel vs known; what must be proven before claiming; reproducibility standards |

**Advanced (what makes juniors dangerous, in the good way):**
| Skill | Content |
|---|---|
| `<project>-<hardest-problem>-campaign` | EXECUTABLE, decision-gated campaign for Phase 1's hardest live problem: numbered phases, exact commands, EXPECTED observations at every gate ("if X instead → branch to Y"), ranked solution menu, wrong paths fenced off, validation-and-promotion through change control |
| `<project>-proof-and-analysis-toolkit` | The domain's first-principles analysis methods, each as a recipe with a worked example from this repo's history |
| `<project>-research-frontier` | Open problems where this project could advance SOTA: why current SOTA fails, this repo's asset, first three concrete steps, falsifiable "you have a result when…" milestone |
| `<project>-research-methodology` | The evidence bar (one mechanism explains ALL observations incl. negatives, survives adversarial refutation); hypothesis-predicts-numbers-first; idea lifecycle |

**Authoring rules (bake into every agent's prompt):**
- Audience: zero-context mid-level engineer or smaller model. Imperative runbook voice; copy-pasteable commands; every jargon term defined once; tables and checklists; each skill states when NOT to use it and which sibling to use instead.
- Scaffold every skill with the **skill-creator** skill's structure: `.claude/skills/<name>/SKILL.md`, YAML frontmatter with `name` and a trigger-rich `description` (exactly when a model should load it), optional `scripts/`/`references/` dirs.
- **GROUND TRUTH ONLY**: verify every command, flag, path, and claim against the repo before stating it. Wrong runbooks are worse than none.
- Embed knowledge; don't reference private/user-specific paths as load-bearing sources.
- Date-stamp volatile facts; end each skill with a "Provenance and maintenance" section containing one-line re-verification commands for anything that may drift.
- No oversell: unproven things stay labeled open/candidate. Nothing may contradict the project's own manifest/rules; no skill may route around its change control.
- **Write ONLY inside `.claude/skills/`** during authoring; the rest of the repo is read-only; no mutating git commands inside agents.

## Phase 3 — Review and fix (after ALL skills exist)

Three parallel reviewers over the complete set, then one fixer:
- **FACTUAL**: re-verify flags/paths/commands/citations against the repo; flag anything invented or stale (severity: would it send an engineer down a wrong path?).
- **DOCTRINE**: contradictions with project rules or between skills; overstated claims; missing gating on anything behavior-changing.
- **USABILITY**: trigger quality of descriptions; duplication (one home per fact, cross-references elsewhere); self-containedness; scannability.

Fixer applies blocking + important fixes. Then report: the skill inventory with one-line descriptions, what was verified by spot-check, and what remains uncertain.

## House rules (post-authoring, this environment)

1. **Git**: after the fixer pass, commit the new `.claude/skills/` content following the repo's branching convention (branch first if on the default branch). `git status` must show changes ONLY under `.claude/skills/` (plus specs below).
2. **SpecKit**: if the repo tracks changes with Spec Kit (`specs/NNN-*/` directories), produce the as-built spec set for the skill-library capability — via `/retro-spec` for mananUtils-family repos, or the repo's own in-repo spec skill where one exists. Commit the specs with or after the skills.
3. **Project-scope boundaries**: all inputs come from the target repo only; never cross-apply another project's artifacts into this repo's skills.

## Provenance

Adapted 2026-07-05 by Claude Fable 5 from the community "retiring distinguished fellow" distillation prompt (r/ClaudeAI, u/Rodbourn), with house rules for this environment. Re-verify the cost warning against current plan limits before quoting numbers.
