# Data Model: Commit Safety Gate

**Feature**: 002-commit-safety-gate | **Date**: 2026-08-24

No database and no persisted runtime state. The only persisted artifacts are the repository
files the scanner reads (tracked content, `.scanignore`) and the ones it never writes (findings
exist only as process output, never as a file). Every entity below is an in-memory object for
the lifetime of one scan invocation.

## Pattern

One named, categorized rule the scanner looks for. The full set is fixed in code (D2); this
table is the reference for what each name means, not a runtime-editable list.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `name` | str | stable identifier used in finding output and in `re:` allowlist entries that target a category by name |
| `category` | `"credential"` or `"identifier"` | the two families from D2 |
| `severity` | `"high"` or `"medium"` or `"low"` | fixed per pattern (see table below); never configurable per repository |
| `matcher` | shape description | what the pattern matches; for `payment_card`, matching also requires the candidate digit string to pass a Luhn checksum, not shape alone |

Revised 2026-08-25 (post-implementation review, FIX-FIRST 5/6/8): three patterns added
(`github_pat`, `google_oauth_token`, `slack_webhook`); `ai_provider_key` renamed `api_key_sk` and
its matcher widened; `aws_access_key` widened to the `ASIA`/`ABIA`/`ACCA` prefixes in addition to
`AKIA`; `pem_private_key` extended to also match a PGP private-key block; `generic_secret_
assignment` tightened (a quoted value may not contain an embedded quote or comma, and a
placeholder-shaped value - `${...}`, `<...>`, `changeme`, and similar - is exempt even when
matched); `aadhaar_in` gained Verhoeff check-digit validation, `iban` gained mod-97 checksum
validation, and `phone_in`/`phone_us`/`payment_card` gained a digit-adjacency boundary
(`(?<![0-9])`/`(?![0-9])`) so a window inside a longer digit run (a hash, an int64 constant) can
no longer match - none of these four are shape-only any more, matching how `payment_card` already
required a Luhn-valid checksum. 15 patterns -> 18.

| `name` | category | severity | matches |
| :--- | :--- | :--- | :--- |
| `github_token` | credential | high | `gh[pousr]_...` |
| `github_pat` | credential | high | `github_pat_...` |
| `aws_access_key` | credential | high | `AKIA...` / `ASIA...` / `ABIA...` / `ACCA...` |
| `google_api_key` | credential | high | `AIza...` |
| `google_oauth_token` | credential | high | `ya29...` |
| `slack_token` | credential | high | `xox[abp]-...` |
| `slack_webhook` | credential | high | `hooks.slack.com/services/T.../B.../...` |
| `api_key_sk` | credential | high | `sk-...` / `sk-live-...` / `sk-test-...` / `sk-ant-...` |
| `jwt` | credential | medium | `eyJ...` three-segment token shape |
| `pem_private_key` | credential | high | a PEM `BEGIN ... PRIVATE KEY` block or a PGP private-key block |
| `generic_secret_assignment` | credential | medium | `password\|passwd\|secret\|api[_-]?key\|token` assigned (`=`, `:`, or `=>`) to a quoted literal of 8+ characters with no embedded quote or comma; a placeholder-shaped capture is exempt |
| `pan_in` | identifier | high | Indian PAN, `[A-Z]{5}[0-9]{4}[A-Z]` |
| `aadhaar_in` | identifier | high | Indian Aadhaar, 12 digits (grouped 4-4-4 or contiguous), Verhoeff-valid |
| `phone_in` | identifier | medium | Indian mobile, `(+91[-.\s]?\|0)?[6-9]\d{4}[-.\s]?\d{5}`, digit-boundary gated |
| `phone_us` | identifier | medium | US phone, `\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}`, digit-boundary gated |
| `email` | identifier | low | an email address not covered by an allowed domain or a no-reply local part (FR-006) |
| `payment_card` | identifier | high | 13-19 digits, digit-boundary gated, Luhn-valid |
| `iban` | identifier | high | IBAN-shaped string, mod-97 checksum valid |

Severity is a fixed property of the pattern, not of any one match: it exists so a future
consumer of the scanner's output (a Director skimming a long finding list, a future CI
annotation) can triage without re-deriving risk from the pattern name. It does not change any
mode's exit code (D4): any finding at any severity is a finding.

## Finding

One match of a Pattern against one location.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `pattern` | `Pattern.name` | which rule matched |
| `severity` | str | copied from the Pattern at report time |
| `file` | str or `"<stdin-hook>"` | the file path, or a fixed marker for the write-time mode, where no file exists yet |
| `line` | int | 1-based line number within the scanned text |
| `masked_snippet` | str | the line with every value matched on it (across every Pattern, not just this Finding's own) replaced by `"****" + value[-2:]` (or `"****"` alone when a value is under 3 characters), longest value first, capped to 200 characters around the first mask marker; never a raw value |

Output line shape (all non-`--stdin-hook` modes): `<file>:<line>: <pattern> (<severity>)
<masked_snippet>`. A Finding is never constructed from a raw value without immediately masking
it: there is no code path that holds the unmasked value longer than the single match-and-mask
step, mirroring the redact-at-construction invariant `headless/preview.py` already uses for
`PreviewRecord` (SC-005). Revised 2026-08-25 (post-implementation review, BLOCK 1): every Finding
on the same line shares one `masked_snippet`, built once from every value matched on that line,
not from each Finding's own single value in isolation - the earlier per-Finding masking left a
second finding's own raw value, or an entirely undetected value, visible in the first finding's
printed line; the 200-character cap around the first match additionally keeps anything outside
that window - detected or not - out of the printed snippet altogether.

## Allowlist entry

One Director-declared exception, read from `.scanignore`.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `kind` | `"exact"` or `"regex"` | `re:<pattern>` lines are `"regex"`; every other non-comment, non-blank line is `"exact"` |
| `value` | str | the literal string (exact) or the pattern text after `re:` (regex) |
| `source_line` | int | line number within `.scanignore`, for error messages if the file is malformed |

A blank line or a line whose first non-whitespace character is `#` is not an Allowlist entry
(comment or spacer). An inline `# scan:allow` marker is not a `.scanignore` entry at all: it is
read directly from the line being scanned, in whichever file or content is being examined, and
suppresses only findings on that line, in that scan. Suppression logic: a Finding is dropped
before being reported if its `masked_snippet`'s source line contains `# scan:allow`, or if the
underlying raw value (checked internally, never re-exposed) exactly equals an `"exact"` entry's
`value`, or matches an `"regex"` entry's `value` as a pattern. `.scanignore` suppression is
global across every scan mode; the inline marker only ever applies to the one scan currently
reading that line.

## ScanMode

Enumeration `staged | paths | history | stdin_hook`, selected by the mutually exclusive CLI
flags (`--staged`, `--paths`, `--history`, `--stdin-hook`); exactly one is required per
invocation.

| Mode | What is examined | Typical caller |
| :--- | :--- | :--- |
| `staged` | added lines of `git diff --cached` | `.githooks/pre-commit` |
| `paths` | complete content of the named files | ad hoc / future scripted use |
| `history` | complete content of every blob in every commit reachable from `HEAD` | `.github/workflows/secret-scan.yml` |
| `stdin_hook` | `tool_input.content` / `.new_string` / `.new_source` from one Claude Code `PreToolUse` payload read from stdin | `.claude/settings.json`'s `PreToolUse` hook |

There is no fifth mode and no mode that writes anything back to the files it scans; the scanner
is read-only in every mode (it never rewrites `.scanignore`, never edits the scanned content,
and never touches git state beyond reading `diff --cached` and commit blobs).

## HookInput

The one piece of state `stdin_hook` mode parses from stdin before it can decide anything.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `raw_bytes` | bytes | read from stdin, decoded UTF-8 with `errors="replace"`, never the platform's default codepage (mirrors `no-em-dash.py`; see `research.md` D1) |
| `parsed` | dict or `None` | `None` when the decoded text does not parse as the expected JSON shape; a `None` here ends the run at "allow, no output" (fail-open) before any other field is read |
| `tool_name` | str or `None` | from `parsed["tool_name"]`; anything other than `Write`, `Edit`, `MultiEdit`, `NotebookEdit` ends the run at "allow, no output" |
| `text_field` | str or `None` | `tool_input.content` (`Write`), `tool_input.new_string` (`Edit`/`MultiEdit`), `tool_input.new_source` (`NotebookEdit`); a missing or non-string value ends the run at "allow, no output" |
| `file_path` | str or `None` | `tool_input.file_path` when present, used only to decide whether the target path is skipped (binary/vendored/gitignored-artifact paths per FR-015); its absence does not block scanning `text_field` |

`HookInput` never itself carries a decision; it is the parsed shape that `Finding` extraction
runs against. A `HookInput` that never reaches a valid `text_field` produces zero Findings by
construction, not by a special-cased early return that could be forgotten in a future edit.

## State transitions (one scan)

```text
parse CLI flags -> exactly one ScanMode selected (argparse enforces this; --stdin-hook takes
   no path arguments, --paths requires at least one)
load .scanignore once (if present; absent is not an error, means zero repository-wide entries)

staged:  git diff --cached (added lines only) -> for each added line, match every Pattern
   -> drop Findings suppressed by .scanignore or an inline marker on that line
   -> print remaining Findings -> exit 1 if any remain, else 0

paths:   for each named file -> skip if binary or an always-skipped path -> match every
   Pattern against the complete content -> suppress -> print -> exit 1 if any remain, else 0

history: for each commit reachable from HEAD -> for each blob in that commit -> skip if
   binary or an always-skipped path -> match every Pattern against the complete blob content
   -> suppress -> print -> exit 1 if any remain, else 0

stdin_hook: read stdin -> decode UTF-8 (replace) -> parse JSON
   -> parse failed, or tool_name not recognized, or text_field absent/non-string,
      or file_path present and skipped: print nothing, exit 0 (allow)
   -> match every Pattern against text_field -> suppress
   -> zero Findings remain: print nothing, exit 0 (allow)
   -> one or more Findings remain: print one JSON object to stdout
      ({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
      "permissionDecisionReason": "<masked findings + how to allowlist>"}}), exit 0 (deny,
      carried in the JSON body per D1's corrected convention - not the exit code)
```

Failure before "load .scanignore" (an unreadable `.scanignore`, a git repository that cannot be
opened for `staged`/`history`) is a usage error, exit `2`, in every mode except `stdin_hook`,
which always resolves to allow-with-no-output rather than ever exiting non-zero or printing to
stderr in a way that could surface as a crash to the assistant (FR-012).
