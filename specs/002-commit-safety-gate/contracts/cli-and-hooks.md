# Contracts: Commit Safety Gate

**Feature**: 002-commit-safety-gate | **Date**: 2026-08-24

Four stable interfaces: the **scanner command line**, the **`.scanignore` grammar**, the **git
pre-commit hook**, and the **Claude Code `PreToolUse` hook** (JSON in, JSON out). The
**CI workflow** that drives the scanner in its `--history` mode is documented last.

## 1. Scanner command line

```text
python scripts/scan_secrets.py --staged
python scripts/scan_secrets.py --paths FILE [FILE ...]
python scripts/scan_secrets.py --history
python scripts/scan_secrets.py --stdin-hook   # reads the hook payload from stdin
```

`--staged`, `--paths`, `--history`, `--stdin-hook` are mutually exclusive; exactly one is
required. `--paths` takes one or more positional-style file arguments after it; the other three
take none.

| Flag | Mode | What is scanned |
| :--- | :--- | :--- |
| `--staged` | staged | added lines of `git diff --cached`, run from the repository root |
| `--paths FILE ...` | paths | complete content of each named file |
| `--history` | history | complete content of every blob in every commit reachable from `HEAD` |
| `--stdin-hook` | stdin_hook | `tool_input.content` / `.new_string` / `.new_source` from one JSON payload read from stdin |

**Exit codes** (`--staged`, `--paths`, `--history` only - `--stdin-hook` never uses these; see
section 4):

| Code | Meaning |
| :--- | :--- |
| `0` | clean: no findings |
| `1` | one or more findings; printed to stdout, none reproduces a raw value |
| `2` | usage error (bad flags, unreadable path, not a git repository for `--staged`/`--history`) |

**Output line format** (`--staged`, `--paths`, `--history`), one line per Finding, to stdout:

```text
<file>:<line>: <pattern-name> (<severity>) <masked snippet>
```

The masked snippet is the matched line with every matched value on that line replaced by
`"****"` plus each value's own last two characters (or bare `"****"` when a value is under 3
characters), longest value first, then capped to 200 characters centered on the first mask
marker; every Finding on a line shares this one snippet. No other line in any mode's output ever
contains a raw finding value. `<file>` for `--history` is `<blob-sha>:<path>` - the short,
8-character **blob** hash, not a commit hash, since `--history` dedupes by blob content
independently of which commit introduced it (`scan_history`'s docstring, D10). To find which
commit(s) introduced a given finding, recover it from the blob sha with
`git log --oneline --find-object=<blob-sha>` (quickstart.md).

## 2. `.scanignore` grammar

Location: repository root, alongside `.gitignore`.

```text
# comment - ignored
ABCDE1234F
director@example.com
super-secret-value-12345
hunter2-XY
re:^test-[a-z]+-[0-9]{4}$
```

| Line form | Meaning |
| :--- | :--- |
| empty, or first non-whitespace character `#` | ignored (comment or spacer) |
| `re:<pattern>` | a regular-expression entry: any matched value the pattern matches is suppressed everywhere |
| anything else | an exact-string entry: a matched value equal to this string is suppressed everywhere |

An allowlist entry suppresses **matched values**, not files or lines: an unrelated occurrence of
a different value that happens to be on the same line, or the same value found in a different
file, is unaffected by an exact-string or regex entry the same way (US4 Acceptance Scenario 1).

**Inline marker**, independent of `.scanignore`: a line containing the literal text
`# scan:allow` anywhere on it (in a comment, in a string, wherever the language allows a `#` to
appear without breaking the file) suppresses every Finding whose `masked_snippet` is drawn from
that line, in that scan only. It requires no entry in `.scanignore` and has no repository-wide
effect (US4 Acceptance Scenario 2).

`.scanignore` itself, and any line containing `re:`/`# scan:allow` as literal example text
inside this very contracts document, are not live entries; only the actual `.scanignore` file at
the repository root is read.

## 3. Git pre-commit hook

File: `.githooks/pre-commit` (POSIX `sh`, executable).

```sh
#!/bin/sh
python3 scripts/scan_secrets.py --staged
```

Exit code propagates directly: a non-zero `scan_secrets.py --staged` (findings, code `1`, or a
usage error, code `2`) refuses the commit; git prints the hook's own stdout (the finding lines)
to the Director's terminal before refusing.

**Activation** (once per clone, not once per commit):

```bash
git config core.hooksPath .githooks
```

Documented as a `README.md` Setup step. `scripts/check_env.py` gains a fifth row:

| Row | PASS when | FAIL hint |
| :--- | :--- | :--- |
| `git_hooks` | `git config core.hooksPath` reports `.githooks` | the exact command above |

## 4. Claude Code `PreToolUse` hook

Registered in the repository's own `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/scripts/scan_secrets.py\" --stdin-hook || exit 0",
            "timeout": 10,
            "statusMessage": "Scanning for credentials and personal identifiers"
          }
        ]
      }
    ]
  }
}
```

**Assumption flagged, corrected 2026-08-25**: `$CLAUDE_PROJECT_DIR` is the variable name this
repository's own `CLAUDE.md` and the global `~/.claude/hooks/no-em-dash.py` already assume Claude
Code exposes to a hook command as the project root; this contract reuses that same assumption
rather than re-verifying it independently (research.md D6). The future-session concern this
section originally flagged was found true during post-implementation review: an invocation
context where `$CLAUDE_PROJECT_DIR` is unset made the command read `/scripts/scan_secrets.py` (an
absolute path from filesystem root), which cannot open, so `python3` exits non-zero and the hook
fails closed - every `Write`/`Edit`/`MultiEdit`/`NotebookEdit` in the session gets blocked, not
just the unsafe ones. The command above now reads `${CLAUDE_PROJECT_DIR:-.}` (falling back to the
invocation's current directory) and ends in `|| exit 0`, so any crash - the variable unset, the
fallback `.` also not being the project root, or anything else - degrades to allow rather than to
block-everything; a real deny is still carried entirely in the JSON body on stdout (D1), never in
the exit code, so `|| exit 0` never masks an actual finding. Proof: `env -u CLAUDE_PROJECT_DIR sh
-c '<the command above>' <<< '{}'` exits `0` from the repository root.

**Input** (stdin, one JSON object, Claude Code's standard `PreToolUse` payload shape):

```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/abs/path/to/file.py",
    "content": "the full text about to be written"
  }
}
```

| `tool_name` | text field read |
| :--- | :--- |
| `Write` | `tool_input.content` |
| `Edit` | `tool_input.new_string` |
| `MultiEdit` | `tool_input.new_string` |
| `NotebookEdit` | `tool_input.new_source` |

Any other `tool_name`, a missing/non-string text field, or a payload that fails to parse as
JSON: no scanning happens; the hook allows silently (exit `0`, no stdout).

**Output on a clean write**: nothing printed, exit `0`. Claude Code proceeds with the write.

**Output on a denied write** (stdout, exit `0` - the deny is carried in the JSON body, not the
exit code; see research.md D1 for why this replaced an earlier exit-code-based design):

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "credential/PII scan found 2 issue(s):\nfile.py:14: api_key_sk (high) key = \"sk-****23\"\nfile.py:22: pan_in (high) pan = \"****4F\"\nIf a match is a known-safe test fixture, add it to .scanignore or mark the line with '# scan:allow'."
  }
}
```

`permissionDecisionReason` is built only from `<file>:<line>: <pattern> (<severity>)
<masked snippet>` lines (the same shape as section 1's stdout format, reusing the same masking
so a Finding is never formatted two different ways) plus one fixed closing line naming both
allowlist mechanisms, so the assistant reading the reason back knows how to resolve a legitimate
exception without needing a second lookup.

**Malformed or unrecognized input**: exit `0`, nothing printed, in every case - stdin that is
not valid JSON, JSON with an unexpected shape, a recognized `tool_name` whose text field is
absent. This mode never exits non-zero and never writes to stderr in a way that would surface as
a crash to Claude Code (FR-012); a mode reaching this hook malformed is fail-open, not the
hook's problem to raise.

## 5. CI workflow

File: `.github/workflows/secret-scan.yml`, triggers `push` and `pull_request`.

| Job | Runner | Steps |
| :--- | :--- | :--- |
| `scan` | `ubuntu-latest`, Python 3.12 | `python scripts/scan_secrets.py --history` -> `python -m pytest -q` -> `python scripts/verify_structure.py` |
| `gitleaks` | `ubuntu-latest` | `gitleaks/gitleaks-action@v2` (no license key; free for a personal-account public repository) |

Playwright browsers are not installed on the `scan` runner; `HEADLESS_TEST_BROWSER` stays unset,
so the opt-in browser suite (`tests/test_gates_browser.py`) is skipped there the same way it is
locally without the flag - this workflow does not change that existing behavior. Either job
failing fails the check; both must be green for the commit gate to be satisfied on a pushed
branch, alongside GitHub's own secret scanning and push protection running independently of both
(research.md, "External control already in place").
