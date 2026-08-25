# Research: Commit Safety Gate

**Feature**: 002-commit-safety-gate | **Date**: 2026-08-24

All Technical Context unknowns are resolved below. Each decision records the choice, the
reason, and the alternatives that were considered and rejected. D1-D10 mirror the decisions
already made before this feature entered planning; D1's write-time (`--stdin-hook`) behavior
carries a correction issued after the initial decision set, folded in below and flagged where
it changed.

## External control already in place

The repository went public on 2026-08-24. GitHub's own **secret scanning** and **push
protection** were enabled on the repository at that time, ahead of this feature's work. This is
existing infrastructure this feature builds around, not something this feature configures: it
is the outermost, host-level backstop that runs independently of anything in this repository's
own tree (User Story 3, FR-014). Nothing in this feature's scope touches GitHub's own scanning
configuration; `research.md` records it here only so later sessions do not rediscover it as an
open question or duplicate it.

## D1. Scanner shape and modes

- **Decision**: one scanner, `scripts/scan_secrets.py`, using only what the project already
  needs to run (no additional installed tool). Four modes: `--staged` (the added lines of
  `git diff --cached`), `--paths <file...>` (the complete content of named files), `--history`
  (every blob reachable from `HEAD`, for CI), and `--stdin-hook` (the Claude Code write-time
  check).
- **Rationale**: one scanner keeps every mode's pattern list and masking logic in one place, so
  a new pattern is added once and every mode gets it. Requiring nothing beyond what the project
  already needs to run means the local refusal, the write-time check, and the CI backstop all
  work identically on a fresh clone with no extra install step to forget, matching the
  repository's existing cross-platform-automation pattern (PATTERNS.md).
- **`--stdin-hook` behavior, corrected**: this mode was first specified as "exit 2 with a
  one-line reason on stderr to deny; exit 0 to allow; never crash the hook on unexpected JSON,
  allow with a note." That shape does not match how Claude Code's own `PreToolUse` hooks work in
  this environment, and it does not match the convention the repository's own house-style hook
  already follows for the exact same problem (blocking a write and explaining why, without
  crashing the assistant's turn). The corrected, final behavior mirrors
  `~/.claude/hooks/no-em-dash.py` exactly:
  - Read stdin as raw bytes and decode as UTF-8 with `errors="replace"`, never using the
    console's default codepage (the house-style hook's own comment explains why: a strict
    decode can raise on the very content the hook exists to catch, and a naive except-and-allow
    around that would make the hook silently do nothing on the platforms most likely to need
    it).
  - On a payload that does not parse as the expected JSON shape, return exit **0** and print
    nothing: a malformed payload is fail-open, not a problem for this hook to raise.
  - Take the text to scan from `tool_input.content` (`Write`), `tool_input.new_string` (`Edit`,
    `MultiEdit`), or `tool_input.new_source` (`NotebookEdit`); any other tool name is skipped
    (exit 0).
  - Skip vendored and binary paths (`is_skipped_path`, shared by every scan mode, not just this
    one). Corrected 2026-08-25 (post-implementation review, FIX-FIRST 9): the original text here
    claimed full parity with the house-style hook's skip convention, including its escape marker;
    the actual, deliberately narrower list is directory names `previews`, `.venv`/`venv`, `.git`,
    `__pycache__`, `.pytest_cache`, `node_modules`, `vendor`, `site-packages`, `.gradle`, `.idea`,
    `.vscode`, `.mypy_cache`; exact lockfile names (`package-lock.json`, `yarn.lock`,
    `pnpm-lock.yaml`, `poetry.lock`, `Cargo.lock`, `gradle.lockfile`, `composer.lock`,
    `Gemfile.lock`); filename suffixes `.map`, `.min.js`, `.min.css`, `.lock`, `.svg`, plus the
    scanner's own pre-existing binary-extension list. Two deliberate differences from the
    house-style hook, both because this is a secret scanner and not a prose-style linter: `dist`,
    `build`, `out`, `target`, and `coverage` are **not** skipped, since generated/bundled code can
    embed a real secret and losing coverage there would be a silent gap in exactly the content
    most likely to have been assembled from a template containing one; and there is **no** escape
    marker (no-em-dash.py's `allow-emdash` equivalent) - an escape hatch that lets content bypass
    a secret scanner by naming a marker in the path or the text is a bypass, not a convenience,
    and the feature already has the correct, narrower escape mechanism for this (the inline
    `# scan:allow` marker on one line, or a `.scanignore` entry for one value - never a path-wide
    opt-out).
  - On a finding, print one JSON object to **stdout** -
    `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
    "permissionDecisionReason": "<masked findings and how to allowlist them>"}}` - and exit
    **0**. The deny is carried in the JSON body, not the process exit code; Claude Code reads
    that body to refuse the write and to feed the reason back to the assistant.
  - On a clean write, print nothing and exit **0**.
  - The reason text is built only from masked snippets (FR-007, FR-011); the raw value is never
    constructed into that string in the first place, so there is no later step that could leak
    it by forgetting to mask.
  - **This coexists with the global `no-em-dash.py` hook**: both are registered as
    `PreToolUse` hooks on `Write|Edit|MultiEdit|NotebookEdit` (the em-dash hook globally in
    `~/.claude/settings.json`, this scanner locally in the repository's own
    `.claude/settings.json`) and both run on every matching write. Either one denying is enough
    to refuse the write; there is no ordering dependency between them, since each reads the same
    stdin payload independently and neither mutates it.
- **Alternatives considered**: a paid or installed third-party scanner (gitleaks, truffleHog)
  as the single tool (rejected for the local/write-time path: not zero-install, and gitleaks is
  confirmed not installed on this machine; kept as a second, independent CI check instead - see
  D7); one exit-code convention across all four modes including `--stdin-hook` (rejected after
  the correction: it does not match how `PreToolUse` hooks communicate a deny in this
  environment, and diverging from the house-style hook's proven convention for the same kind of
  gate would mean two different mechanisms doing the same job in the same tree); separate
  scripts per mode (rejected: duplicates the pattern list and masking logic four ways).

## D2. Detections

- **Decision**: two families of named, severity-carrying patterns.
  - Credentials: GitHub tokens (`gh[pousr]_...`), AWS access keys (`AKIA...`), Google API keys
    (`AIza...`), Slack tokens (`xox[abp]-...`), OpenAI/Anthropic-shaped keys (`sk-...`,
    `sk-ant-...`), JWTs (`eyJ...`), PEM private-key blocks, and a generic
    `password|passwd|secret|api[_-]?key|token` assignment to a quoted literal of 8 or more
    characters.
  - Personal identifiers: Indian PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (12 digits, grouped
    4-4-4 or contiguous), Indian mobile numbers (`(+91|0)?[6-9]\d{9}`), US phone numbers
    (`\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}`), email addresses, payment card numbers (13-19 digits
    that pass a Luhn checksum), and IBAN-shaped strings.
- **Rationale**: this list covers every category of value `CLAUDE.md`'s Secrets section already
  names as never allowed in the repository (PAN, Aadhaar, passport-adjacent identifiers, card
  data, passwords), plus the credential shapes most likely to appear by accident in a personal
  automation tool (a pasted API key, a token left in a comment). Luhn validation on card numbers
  keeps the false-positive rate on ordinary 13-19 digit numbers (order IDs, tracking numbers)
  low without needing a lookup table.
- **Alternatives considered**: entropy-based generic-secret detection (higher recall on unknown
  secret shapes, but a much higher false-positive rate on this repository's own test fixtures
  and hex/base64 fixtures; rejected for a personal tool where the known-shape list already
  covers every real secret type this repository handles); a maintained third-party pattern
  database (more categories, but reintroduces a dependency and an update cadence for a
  zero-install tool); passport numbers (no single reliable shape across issuing countries;
  covered instead by the generic `secret`/`token`-style assignment pattern when a script
  variable is literally named `passport_number` or similar, and by the Director's own review).

## D3. Allowlist

- **Decision**: `.scanignore` at the repository root, one entry per line, each entry either an
  exact string or `re:<pattern>`; `#` starts a comment. An inline `# scan:allow` marker on a
  line suppresses findings on that line only, wherever it appears, without touching the
  repository-wide file. Binary files and the `previews/`, `.venv/`, `.git/` paths are always
  skipped regardless of the allowlist. `.scanignore` ships seeded with the fixtures the
  feature's own test suite needs to use safely: `ABCDE1234F`, `director@example.com`,
  `super-secret-value-12345`, `hunter2-XY`. (A seventh
  entry, `Director Name`, was seeded here too but removed 2026-08-25 (post-implementation
  review, NIT-12): no pattern this scanner defines can ever match a plain two-word name, so it
  was never a real exception.)
- **Rationale**: two mechanisms cover the two shapes of exception the repository actually
  needs: a small, auditable, repository-wide list for values that recur across multiple test
  fixtures (a synthetic PAN used in three different test files), and an in-place marker for a
  one-off line that would otherwise need a repository-wide entry for a value nobody else will
  ever reuse. Neither weakens the pattern itself; both suppress specific matches, so an
  unrelated real occurrence of the same shape elsewhere is still caught (FR-008, US4).
- **Alternatives considered**: inline suppression only, no repository-wide file (rejected: would
  force the same synthetic PAN to be marked in every file it appears in, with no single place to
  audit what is exempted); a repository-wide file only, no inline marker (rejected: forces every
  one-off exception into the shared file, growing it with entries relevant to a single line);
  a severity threshold instead of an allowlist (rejected: would suppress a whole pattern's
  matches everywhere, not just the known-safe occurrence).

## D4. Output and exit codes

- **Decision**: every finding line is `<file>:<line>: <pattern-name> (<severity>) <masked
  snippet>`, where the matched value is replaced by `****` plus its own last two characters -
  never the raw value, at any severity, in any mode. Exit codes in the non-hook modes: `0`
  clean, `1` findings present, `2` usage error. (`--stdin-hook`'s own signaling is D1's
  corrected JSON-on-stdout convention, not this exit-code table - see D1.)
- **Rationale**: matches the masking convention `PATTERNS.md` already documents for preview
  artifacts (`redact(value) = "****" + value[-2:]`), so a Director already familiar with how
  Headless masks a value recognizes the same shape here. Standard `0`/`1`/`2` exit codes let the
  pre-commit hook and the CI job branch on outcome with no output parsing.
- **Alternatives considered**: showing the full matched value in local-only output (rejected:
  the whole point of the gate is that a value never needs to appear anywhere, including a
  terminal a Director might screen-share or paste into a bug report); a single boolean exit code
  with no distinction between "found something" and "used it wrong" (rejected: `verify_structure
  .py` and the rest of the repository's own tooling already use `2` for usage errors, and a
  distinct usage-error code catches a scanner invoked wrong before it is mistaken for "scan
  passed").

## D5. Git pre-commit hook

- **Decision**: `.githooks/pre-commit`, a POSIX `sh` script running
  `python3 scripts/scan_secrets.py --staged` and exiting non-zero on findings. Activated per
  clone by `git config core.hooksPath .githooks`, documented as a Setup step in `README.md`.
  `scripts/check_env.py` gains a fifth row, `git_hooks`, `PASS` when `core.hooksPath` is
  `.githooks` and `FAIL` with the exact activation command as the hint otherwise.
- **Rationale**: `core.hooksPath` is a per-clone, one-time git configuration, not a file that
  git can be told to run automatically from a tracked path (git never executes a tracked
  `.git/hooks` file for security reasons) - the one-time activation step is unavoidable in
  standard git, which is why FR-010 and FR-017 both call it out explicitly and why the
  self-test row exists: without it, a Director could believe the local refusal is active on a
  fresh clone when it is not (spec Edge Case, US1 Acceptance Scenario 5).
- **Alternatives considered**: a git template directory pre-seeding hooks for every future
  `git init`/`git clone` on the machine (rejected: machine-wide, not repository-scoped, and
  invisible in `Project_Structure.md`); a `pre-commit` framework config (rejected: an
  installed dependency, against the zero-install constraint); committing directly into
  `.git/hooks/` (impossible - that directory is never tracked by git).

## D6. Claude Code layer

- **Decision**: a committed `.claude/settings.json` registering a `PreToolUse` hook, matcher
  `Write|Edit|MultiEdit|NotebookEdit`, command
  `python3 "$CLAUDE_PROJECT_DIR/scripts/scan_secrets.py" --stdin-hook`.
- **Rationale**: `$CLAUDE_PROJECT_DIR` is the environment variable Claude Code exposes to hook
  commands with the project root, confirmed by its use in this same form in the global
  `no-em-dash.py`'s own installation convention (`~/.claude/settings.json`) referenced in this
  repository's `CLAUDE.md`; using it keeps the hook command correct regardless of the working
  directory a given Claude Code invocation starts from, including from inside a worktree such as
  this one. This assumption is carried over from an already-working sibling hook rather than
  independently re-verified in this feature; if a future session finds `$CLAUDE_PROJECT_DIR`
  unset in some invocation context, `scripts/scan_secrets.py --stdin-hook` should be made to
  fall back to locating the repository root the same way `scripts/check_env.py` already does
  (walking up from `__file__`), rather than assuming the variable is always present.
- **Alternatives considered**: a hard-coded absolute path (rejected: breaks the moment the
  worktree or clone location changes, which happens on every new version branch in this
  repository's own git-flow); a relative path from an assumed working directory (rejected: hook
  commands are not guaranteed to run from the repository root).
- **Scope fact, verified during implementation**: this repository's `.claude/settings.json`
  only fires for a Claude Code session whose project root is this repository (this worktree or
  another checkout of it) - a session started elsewhere, working on this repository's files
  indirectly or not at all, never sees this hook. A commit from such a session, or from any
  path this hook does not cover, still relies on the local git hook (D5) and the CI backstop
  (D7) as documented; this write-time layer is a narrowing of coverage to "when Claude Code is
  actually working in this repository," not a claim that it covers every way content could
  reach this repository.

## D7. CI backstop

- **Decision**: `.github/workflows/secret-scan.yml`, triggered on `push` and `pull_request`.
  Job 1 (`ubuntu-latest`, Python 3.12, no Playwright browsers installed - the browser suite
  stays skipped): `python scripts/scan_secrets.py --history`, then
  `python -m pytest -q`, then `python scripts/verify_structure.py`. Job 2: `gitleaks
  /gitleaks-action@v2`, free for a personal account, no license key required.
- **Rationale**: `--history` is the one mode this repository's own scanner runs only in CI - a
  full-history scan is not something a Director wants on every local commit (D1's `--staged`
  mode exists precisely to keep that fast), but it is exactly what a backstop for a public
  repository needs, since it catches a secret that entered history before this feature existed,
  or on a machine where the local hook never ran. Running the repository's own pytest suite and
  `verify_structure.py` in the same job keeps the whole commit gate (constitution Lesson 4)
  enforced in CI, not just locally. A second, independent tool (`gitleaks`) in its own job adds
  a maintained pattern database this repository's own hand-written patterns cannot match line
  for line, at the same zero cost.
- **Alternatives considered**: one combined job (rejected: a `gitleaks` action failure and a
  scanner/test failure would be harder to tell apart in the checks list); a paid scanning
  service (rejected: `gitleaks-action` is free for a public repository on a personal account,
  the same $0 target the constitution's Lesson 5 already applies to cloud resources); running
  `--history` locally too (rejected: too slow for every commit, and redundant with `--staged`
  covering the same new content before it is committed).

## D8. Tests

- **Decision**: `tests/test_scan_secrets.py` proves: every named pattern is detected on a
  synthetic sample and stops being detected once that sample is allowlisted; Luhn validation
  rejects a random 16-digit number that is not a valid card number; masking never leaks the
  underlying value in any output path; `--stdin-hook` denies a `Write` containing a PAN (its
  JSON output carries `permissionDecision: "deny"`, per D1's corrected shape) and allows a clean
  one through with no output; `--staged` on a temporary git repository with a staged secret
  exits `1`; `--history` on this repository's own real history exits `0` (the history is known
  clean); the scanner completes a full-tree scan in under 2 seconds.
- **Rationale**: this is the same shape of proof `constitution.md`'s Principle IV already
  requires of every errand (pure logic unit-tested, the live behavior proven read-only) applied
  to a maintenance script instead of an errand: every detection category and every failure mode
  named in the spec's Success Criteria (SC-001 through SC-006, SC-008) has a corresponding test,
  and none of them requires a real secret.
- **Alternatives considered**: testing only that the scanner runs without error (rejected: would
  not prove any individual pattern actually fires, defeating the point of the feature);
  asserting on exact masked output strings only, without also asserting the raw value's absence
  (rejected: a test could pass on a coincidentally-correct mask while the raw value leaked
  elsewhere in the same output).

## D9. Docs of record

- **Decision**: this feature's implementation phase updates, in the same change: `CLAUDE.md`'s
  Lesson 4 gate sentence, to name the scanner as part of every commit and the `.githooks`
  activation as mandatory on every clone; `.specify/memory/constitution.md`, bumped to 1.2.0
  (MINOR) with a Sync Impact Report line; `PATTERNS.md`, a new "Commit safety gate (v0.0.2)"
  entry; `README.md`, a new Setup step for `.githooks` activation and a "Public repo hygiene"
  section; `scripts/README.md`, a Maintenance row for `scan_secrets.py`; `Project_Structure.md`,
  Director-layer rows for `.githooks/`, `.github/`, `.scanignore`, `.claude/settings.json`, and
  a v0.0.2 Changelog row listing every new file. `terraform/README.md` is unchanged: this
  feature creates no cloud resource.
- **Rationale**: mirrors constitution Principle I (every file addition logged in the same
  change) and Principle II (`PATTERNS.md` reflects only the actual codebase). `Function_Mapping
  .md` is deliberately not touched: `scan_secrets.py` is a maintenance script like
  `check_env.py`, not a site-driving errand, and `scripts/README.md` already documents that
  distinction for `check_env.py`.
- **Alternatives considered**: a MAJOR constitution bump (rejected: this feature adds a new hard
  rule about how a commit is made, but does not remove or redefine any existing principle or
  hard rule - MINOR is the correct bump per the constitution's own Governance section);
  documenting the gate only in `README.md` (rejected: `CLAUDE.md` is the constitution of record
  and the place every session is told to read first; leaving it out there would mean a future
  session inherits the rule only by accident).

## D10. Out of scope

- **Decision**: this feature does not rewrite existing repository history, does not scan the
  Chrome profile directory or `previews/` content, does not adopt a paid third-party scanner,
  and does not configure any organization-level GitHub policy.
- **Rationale**: `--history` scans forward from what already exists; the assumption recorded in
  the spec is that the fixtures seeded into `.scanignore` are the only known matches in the
  current history, verified in D8's test that `--history` on this repository's own real history
  exits `0`. Rewriting history is a separate, higher-risk operation the Director has not asked
  for. `previews/` and the Chrome profile are already gitignored and already documented as
  vault-grade local data in `CLAUDE.md`; scanning them would be scanning data that never reaches
  a commit in the first place, outside this feature's actual threat model (a value reaching
  public git history). Org-level policy is not applicable: this is a personal account, not an
  organization.
- **Alternatives considered**: none seriously considered; each of these was named explicitly by
  the orchestrator as out of scope before this research began.
