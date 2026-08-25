# Contracts: Login Persistence

**Feature**: 003-login-persistence | **Date**: 2026-08-25

Three stable interfaces: the **state file** itself, the **`Session` import/export behavior** per
mode and per path, and the **sandbox launch option** contract. There is no CLI surface change and
no new hook: this feature adds no flag, no environment variable, and no `argparse` argument
anywhere (spec FR-002).

## 1. The state file

| Property | Value |
| :--- | :--- |
| Path | `<profile_dir>/session-cookies.json`, where `profile_dir` is `Config.profile_dir` (`headless/config.py`, resolved from `HEADLESS_PROFILE_DIR`/`--profile-dir`, default `~/.headless/chrome-profile`) |
| Format | a single JSON array; each element is a `SessionCookieEntry` (data-model.md), the same shape `context.cookies()` returns |
| Permissions | `0600`, enforced on every export, whether the file is being created or replaced |
| Written by | `Session.__exit__`, launched-profile path only, before `context.close()` |
| Read by | `Session.__enter__`, launched-profile path only, immediately after launch and before any navigation |
| Never written by | the CDP-attach path, in any mode |
| Never read by | anything other than `Session.__enter__` on the launched-profile path; no other script or module in this codebase opens this file |

**What a reader may assume**: if the file exists and parses as the expected shape, every entry in
it satisfies `expires == -1` (the export side never writes anything else). A reader MUST NOT
assume the file exists at all (a fresh or never-run profile has none) and MUST NOT assume its
absence means anything went wrong (FR-006). A reader MUST NOT assume the file's on-disk
permission mode is already `0600` before the first export corrects it (research.md D6's
"wrong mode" test case: an externally-created or older-version file may exist at a looser mode;
import still reads it, and the next export corrects the mode).

**What a reader may never assume**: that the file's content is safe to print, log, or include in
any preview artifact. Every value in it is exactly the kind of typed value `CLAUDE.md`'s Secrets
section already governs; nothing about this file changes that classification.

## 2. `Session` behavior contract

### Import (`__enter__`, launched-profile path only)

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| No state file at the profile's path | No action taken. | Nothing printed. Context has whatever cookies Chrome's own profile already restored (non-session cookies only, per the root cause). |
| State file exists, parses, `context.add_cookies()` accepts every entry | Entries are handed to `context.add_cookies()` once, as a single call. | Nothing printed on success. Context now also holds the restored session cookies. |
| State file exists but cannot be opened or read (`OSError`) | Caught. | Exactly one line: `note: session cookies not restored (<ExceptionClassName>)`. Context unaffected beyond what Chrome's own profile already restored. |
| State file exists but is not valid JSON, or is valid JSON that is not a list of entries | Caught. | Same one-line note as above, with the parsing exception's class name. |
| State file is present but empty (zero bytes) | Treated as a parse failure (fails the same JSON decode step as malformed content). | Same one-line note. |
| State file parses fine, but `context.add_cookies()` raises for the call as a whole | Caught. | Same one-line note (`add_cookies`'s own exception class name); zero cookies imported this run, not a partial set. |

In every failure row, exactly one note line is printed and `__enter__` still returns a usable
`Session`; import failure is never fatal to a run (spec User Story 3, Acceptance Scenario 3-4).

### Export (`__exit__`, launched-profile path only, before `context.close()`)

| Input state | Behavior | Output / observable effect |
| :--- | :--- | :--- |
| Context closes normally, holds zero or more session cookies | `context.cookies()` is read, filtered to `expires == -1`, written to a temp file in `profile_dir`, then atomically replaced onto the state file's path, then `chmod 0600`. | Nothing printed on success. File exists (possibly `[]` if there were no session cookies) at mode `0600`. Any cookie the file previously listed but the context no longer holds is absent from the new file. |
| The write itself fails (directory unwritable, disk full, permission error, or any other `OSError` at any step of the temp-file-then-replace sequence) | Caught. | Exactly one line: `note: session cookies not saved (<ExceptionClassName>)`. `context.close()` still runs immediately after; the run's exit code and every other output are unaffected. |

Export never retries (`NFR-002`); a failure is reported once, on the first attempt, and the
session still closes cleanly (spec User Story 3, Acceptance Scenario 5).

### Per mode

Import and export behave identically across preview, check, and apply: neither function branches
on `self.mode` at all. The only branch that matters is launched-profile versus CDP-attach (below).
Every clean close, in every mode, attempts an export (spec FR-003); every launch, in every mode,
attempts an import.

### Per path

| Path | Import | Export |
| :--- | :--- | :--- |
| Launched profile (`config.cdp_url` is `None`) | Runs, per the table above. | Runs, per the table above. |
| CDP attach (`config.cdp_url` is set) | Never runs. No file is opened, read, or referenced in any way. | Never runs. No file is opened, written, or referenced in any way. |

The CDP-attach row is absolute: there is no failure mode, no flag, and no configuration that
causes the CDP-attach path to touch the state file (spec FR-012, SC-006).

### Note-line wording, exact

The only two note lines this feature ever prints, verbatim except for the exception class name:

```text
note: session cookies not restored (<ExceptionClassName>)
note: session cookies not saved (<ExceptionClassName>)
```

Neither line, under any input, ever contains a cookie name, a cookie value, the raw text of the
state file, or the caught exception's own message - only its class name (research.md D4). This
mirrors the existing convention `Session.screenshot()` already established for its own
CSP-blocked-mask note (`note: screenshot skipped, the page's CSP blocked the mask`): one fixed,
value-free sentence per failure class, printed to stdout, never to a raised exception a caller
would have to specifically catch to avoid crashing.

## 3. Sandbox launch contract

| Call site | Before this feature | After this feature |
| :--- | :--- | :--- |
| `headless/session.py`, `Session.__enter__`, `launch_persistent_context(...)` | no `chromium_sandbox` argument passed (Playwright default: adds `--no-sandbox`) | `chromium_sandbox=True` passed explicitly |
| `scripts/check_env.py`, `_check_browser()`, `p.chromium.launch(channel="chrome", headless=True)` | no `chromium_sandbox` argument passed | `chromium_sandbox=True` passed explicitly |

**Contract**: every Chrome process this codebase launches is started with the sandbox on;
`--no-sandbox` never appears on the command line of any Chrome process Headless starts. There is
no flag, environment variable, or code path that disables this. A unit test proves the contract by
monkeypatching the launch call and asserting `chromium_sandbox is True` in the captured keyword
arguments, for both call sites (spec SC-002).

The CDP-attach path is out of scope for this contract: `connect_over_cdp` does not launch a
Chrome process at all, it attaches to one the Director already started, so there is no launch
option for this feature to set there.
