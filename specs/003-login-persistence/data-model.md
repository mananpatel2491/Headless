# Data Model: Login Persistence

**Feature**: 003-login-persistence | **Date**: 2026-08-25

No database. The only persisted artifact is the state file this feature introduces
(`<profile_dir>/session-cookies.json`); everything else here is in-memory for the lifetime of one
`Session`. The state file's own content shape and invariants are the entire data model.

## SessionCookieState

The complete content of the state file: a JSON array of `SessionCookieEntry` records, nothing
else. There is no wrapping object, no version field, no metadata - the file's whole content is
the array, matching the shape `context.cookies()` already returns so the array can be filtered
and written directly, and read back and handed to `context.add_cookies()` directly.

| Field | Type | Rules |
| :--- | :--- | :--- |
| (the file's root value) | `list[SessionCookieEntry]` | every element MUST satisfy `expires == -1` (D3); the array MAY be empty (a context with no session cookies at close writes `[]`, not an absent file) |

**Invariant - session cookies only**: an entry with any expiry other than `-1` MUST NOT appear in
the file. Chrome's own persistent profile already keeps a cookie that carries an expiry across a
restart (root-cause evidence, research.md), so writing it here would be redundant at best and a
second, potentially stale copy of a value Chrome itself already owns at worst.

**Invariant - whole-file replace**: every export overwrites the file's entire previous content
with exactly what `context.cookies()` returns at that close, filtered to session cookies. There is
no merge step and no accumulation across runs; the file after export N reflects only what the
context held at the end of run N.

**Invariant - file mode**: the file MUST exist at permission mode `0600` after any export,
whether being created for the first time or replacing an existing file at a looser mode.

**Invariant - atomic write**: at no point may a partial or truncated file exist at the state
file's path; the write goes to a temporary file in the same directory, then an atomic replace
(`os.replace`) puts it at the final path in one filesystem operation.

## SessionCookieEntry

One cookie record, the same shape Playwright's `context.cookies()` produces and
`context.add_cookies()` accepts, so no translation happens between what the browser returns and
what the file stores.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `name` | str | the cookie's name; never itself treated as sensitive for masking purposes (a cookie's name is typically a fixed, non-secret label such as `session_id`; only `value` is redaction-worthy the way the rest of this codebase treats a typed value) |
| `value` | str | the cookie's value; this is the field every failure-handling rule in `research.md` D4 exists to keep out of any printed output |
| `domain` | str | the cookie's scope; read and written as-is, never inspected or filtered by this feature beyond what `context.cookies()`/`add_cookies()` already require |
| `path` | str | the cookie's path scope; read and written as-is |
| `expires` | float | Playwright's marker: `-1` for a session cookie, any other value is a Unix timestamp for an expiring cookie. This is the field the export filter tests (`expires == -1`); an entry with any other value is never written to the file in the first place |
| `httpOnly` | bool | carried through unchanged; not inspected by this feature |
| `secure` | bool | carried through unchanged; not inspected by this feature |
| `sameSite` | `"Strict"` \| `"Lax"` \| `"None"` | carried through unchanged; not inspected by this feature |

This feature never constructs a `SessionCookieEntry` from scratch: every entry in the file either
came from `context.cookies()` verbatim (export) or is handed to `context.add_cookies()` verbatim
after being read back (import). There is no field this feature adds, renames, or derives.

## Session lifecycle: state transitions with import/export added

`Session`'s existing `__enter__`/`__exit__` state machine (`headless/session.py`) gains exactly
two new steps, both confined to the launched-profile branch (the CDP-attach branch is untouched,
D1):

```text
__enter__ (launched-profile branch only):
  start Playwright
  ensure profile_dir exists
  launch_persistent_context(profile_dir, channel="chrome", headless=headless_flag,
                             chromium_sandbox=True)                          # D7
  page = context.pages[0] or context.new_page()
  IMPORT: if <profile_dir>/session-cookies.json exists ->
     parse it -> context.add_cookies(entries)                                # D3, D6
     on any failure (missing file: skip silently, no note;                   # D4
                     unreadable/malformed/empty file, or add_cookies itself
                     raising): catch, print at most one note, continue with
                     zero cookies imported this run
  if should_hide_window(mode, config): _hide_window()
  return self

... goto() / probe() / fill() / screenshot() / handoff(), unchanged ...

__exit__ (launched-profile branch only, before context.close()):
  EXPORT: cookies = context.cookies()
     session_only = [c for c in cookies if c["expires"] == -1]               # D3
     write session_only to a temp file in profile_dir, then os.replace onto
     <profile_dir>/session-cookies.json, then chmod 0600                     # FR-005
     on any failure (unwritable directory, disk full, etc.):
        catch, print exactly one note, continue to context.close() anyway    # D4, NFR-002
  context.close()

__enter__ / __exit__ (CDP-attach branch): unchanged. Neither IMPORT nor EXPORT ever runs here.
   (D1, FR-012)
```

**Ordering guarantee**: IMPORT always completes (successfully or by falling back to "zero cookies
imported") before `__enter__` returns, so no caller can ever observe a `Session` whose context has
only partially received its restored cookies. EXPORT always attempts to run before
`context.close()`, so the file on disk after a clean `__exit__` reflects the context's state at
the moment it was still open, not a stale snapshot from an earlier point in the run.

**Failure isolation**: a failure in IMPORT never prevents `__enter__` from completing and
returning a usable `Session` (the run proceeds logged out, exactly as if this feature did not
exist). A failure in EXPORT never prevents `__exit__` from reaching `context.close()` and, in the
CDP-attach branch's equivalent path, `_browser.close()` - the existing teardown guarantee that
stops the Playwright driver in a `finally` block is unaffected by anything this feature adds.
