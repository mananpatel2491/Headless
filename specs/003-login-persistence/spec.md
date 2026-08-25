# Feature Specification: Login Persistence

**Feature Branch**: `v0.0.3` (spec directory `003-login-persistence`)

**Created**: 2026-08-25

**Status**: Draft

**Input**: User description: "UAT of v0.0.1 (2026-08-25): the Director ran check_env (5/5 PASS),
a plain preview (no window, correct), and a probe --apply against
https://www.progressive.com/ (window stayed hidden until 'Your turn', correct). He logged in by
hand and pressed Enter. A following preview run of the same site showed a logged-out page: the
login did not persist. Root cause confirmed by the orchestrator: Chrome drops cookies that carry
no expiry (session cookies, which is what most logins set) on every persistent-context restart,
even though cookies with an expiry survive; a Playwright storage-state export at close plus
add_cookies at the next launch restores both kinds. Separately, the apply window showed Chrome's
'unsupported command-line flag: --no-sandbox' warning bar; root cause confirmed as Playwright
adding --no-sandbox to every launch unless chromium_sandbox=True is passed. Fix both: persist
session cookies across runs on the launched-profile path only, and pass chromium_sandbox=True on
every Chrome launch in the codebase."

## Why

A login that does not survive between runs defeats the point of a persistent Chrome profile:
every errand that needs the Director logged in would need him to log back in by hand on every
single invocation, which is exactly the friction the profile was built to remove. The Director
confirmed this in UAT the day after v0.0.1 shipped: he seeded a login on progressive.com, and the
very next preview run showed him logged out again. The `--no-sandbox` warning bar is a smaller
problem on its own, but it appears in the one window the Director is looking at directly (the
apply handoff), and a stability-and-security warning printed by the browser itself, on every
apply run, is not a good first impression of a tool that already asks him to trust it with his
logins.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A seeded login persists to the next run (Priority: P1)

The Director runs `probe <site> --apply`, logs in by hand at the "Your turn" prompt, and presses
Enter. He later runs `probe <site>` (preview) or `probe <site> --apply` again. The page loads
already logged in, the same way it would in a browser he never closed.

**Why this priority**: this is the defect the Director actually hit and reported. Without it, the
persistent profile only ever half-works: it happens to keep whatever a site stores in a
long-lived cookie, but drops the part of a login that almost every site actually uses to decide
"is this person signed in".

**Independent Test**: seed a login on a page that sets a session cookie (no expiry) through
`document.cookie`, close the session, relaunch on the same profile, and confirm the cookie is
present in the relaunched context.

**Acceptance Scenarios**:

1. **Given** a launched-profile session that closes cleanly after a page sets a cookie with no
   expiry, **When** a later run opens the same profile directory, **Then** that cookie is present
   in the new browser context before the run navigates anywhere.
2. **Given** a launched-profile session where the site never sets a cookie with no expiry (the
   whole login lived in a cookie that already carries an expiry), **When** a later run opens the
   same profile, **Then** that cookie is present anyway, because Chrome already keeps it itself;
   this feature does not need to touch it.
3. **Given** a session whose site cleared or changed the session cookies it had earlier set,
   **When** that session closes, **Then** the next run's restored set reflects only what the site
   still had at close, not a stale value from an earlier run.
4. **Given** the CDP-attach path (`HEADLESS_CDP_URL` set, attaching to the Director's own running
   Chrome), **When** a session opens or closes, **Then** nothing in this feature reads or writes
   any file, and the attached browser's own cookie jar is left exactly as the Director's Chrome
   manages it.

---

### User Story 2 - The apply window shows no sandbox warning (Priority: P2)

The Director watches the apply window at the handoff. Chrome's own "unsupported command-line
flag: --no-sandbox" warning bar is absent.

**Why this priority**: cosmetic next to User Story 1, but it is the one thing the Director
actually sees on screen during every apply run, and an unexplained browser-security warning in a
tool that types into his logged-in accounts is a bad look worth a one-line fix.

**Independent Test**: launch the profile the way `session.py` does for a real run and confirm
`--no-sandbox` is not among the Chrome process's command-line arguments.

**Acceptance Scenarios**:

1. **Given** any launched-profile Chrome session (preview, check, or apply), **When** Chrome
   starts, **Then** `--no-sandbox` is not present in its command line and no unsupported-flag
   warning bar appears.
2. **Given** `scripts/check_env.py`'s browser-reachability probe, **When** it launches Chrome
   briefly to confirm the `chrome` channel resolves, **Then** it launches the same way (sandbox
   on), for the same reason, even though that launch is never seen by the Director.

---

### User Story 3 - The persisted state file is safe (Priority: P1)

The file this feature writes holds plaintext cookie values, the same class of data the Director's
whole Chrome profile directory already holds. It never becomes more exposed than that profile
already is, it never appears in anything the Director reads on a terminal, and a problem reading
or writing it never breaks an errand run.

**Why this priority**: this feature's entire value proposition (User Story 1) is worth nothing if
delivering it also means a cookie value could end up printed to a terminal, committed to the
repository, or left readable by another local account. It ranks with User Story 1, not below it,
because a persistence feature that is not safe is not a feature to ship at all.

**Independent Test**: run an export, inspect the resulting file's permission bits and location,
and confirm no note, error message, or preview artifact produced anywhere in the run contains a
cookie name or value.

**Acceptance Scenarios**:

1. **Given** a launched-profile session closes cleanly, **When** the export writes its file,
   **Then** the file lands at `<profile_dir>/session-cookies.json`, is created (or left) at file
   mode `0600`, and was written atomically (never observable as a half-written file at that
   path).
2. **Given** the state file does not exist yet (a fresh profile, or one never seeded), **When** a
   session opens, **Then** the run proceeds logged out with no error and no note; a missing file
   is the expected first-run state, not a fault.
3. **Given** the state file exists but cannot be parsed (corrupted, truncated, or not valid JSON
   for the shape this feature expects), **When** a session opens, **Then** the run proceeds
   logged out, prints exactly one note naming the reason class, and never reproduces any byte of
   the file's contents in that note.
4. **Given** the browser rejects one or more entries read from the state file when they are
   handed back to it, **When** that happens, **Then** the run proceeds logged out for this
   session, prints exactly one note, and does not crash or abort the run.
5. **Given** a session closes but the export write itself fails (for example, the profile
   directory has become unwritable), **When** that happens, **Then** the run still closes
   cleanly, exactly one note is printed, and no partial or malformed file is left in the export's
   place.

---

### Edge Cases

- The state file exists but its on-disk permission bits are looser than `0600` (for example, an
  operator manually created it, or an earlier tool version wrote it differently): the file is
  still read; only the export step enforces `0600`, correcting a looser mode on its next write.
- A site's own bot defense treats the headless preview/check user agent (which still identifies
  as `HeadlessChrome` on this machine, per `PATTERNS.md`'s "Quiet by default" entry) as suspicious
  and logs the profile out server-side: the next export faithfully writes whatever session cookies
  remain, which may be none; this is an accepted residual, not a defect in this feature, and the
  recovery is the same `--apply` seed the Director already knows.
- A site's login lives entirely in `sessionStorage` (a JWT, for example) rather than in a cookie:
  this feature does not persist it, by design; see Out of Scope.
- Two concurrent runs on the same profile directory: unaffected by this feature and unchanged by
  it; the existing profile-lock `GateRefused` (`PATTERNS.md`'s Chrome profile-lock entry) already
  covers that case before either run reaches the import step.
- A cookie in the state file has a value under three characters: masking in any note or debug
  output still never shows more of it than the existing `redact()` convention already allows for
  any short value elsewhere in the codebase.
- `HEADLESS_PROFILE_DIR` is pointed at a path inside the repository: the state file this feature
  writes there is excluded from version control the same way the rest of the profile directory
  already is, as a second line of defense alongside the directory itself normally being outside
  the repository.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: On the launched-profile path only (no `HEADLESS_CDP_URL` configured), immediately
  after a successful browser launch and before any navigation, the system MUST attempt to import
  previously exported session cookies into the new browser context, if a state file exists for
  that profile directory.
- **FR-002**: The state file's location MUST be derived from the profile directory already in
  use (`<profile_dir>/session-cookies.json`) with no new environment variable and no new CLI
  flag.
- **FR-003**: On every clean close of a launched-profile session, in every mode (preview, check,
  apply), the system MUST export the browser context's current cookies to the state file, writing
  only the entries that carry no expiry (session cookies); an entry that already carries an
  expiry MUST NOT be written, because Chrome's own persistent profile already keeps it.
- **FR-004**: Each export MUST replace the state file's entire previous content, not merge with
  it, so that a cookie a site has since cleared no longer appears in the file after the run that
  observed it gone.
- **FR-005**: The export MUST be written atomically (a temporary file in the same directory,
  then an atomic replace of the target path) and MUST result in the file existing at permission
  mode `0600`, whether the file is being created for the first time or replaced.
- **FR-006**: A state file that is missing MUST NOT be treated as an error and MUST NOT produce
  any note or message; the run proceeds logged out with no output about it.
- **FR-007**: A state file that exists but cannot be read or parsed as the expected shape MUST
  NOT fail the run: the system MUST print exactly one note naming the reason class and continue
  the run logged out.
- **FR-008**: If the browser rejects one or more cookie entries read from the state file when
  they are handed to it, the system MUST catch that failure, print exactly one note, and continue
  the run rather than raising or aborting it.
- **FR-009**: An export that fails to write MUST NOT fail the run: the system MUST print exactly
  one note and the session MUST still close cleanly, exactly as it would if no persistence
  feature existed at all.
- **FR-010**: No note or message produced by the import or export path MUST ever contain a cookie
  name or a cookie value, in any run, in any mode.
- **FR-011**: `.gitignore` MUST exclude the state file's name so that a `HEADLESS_PROFILE_DIR`
  pointed inside the repository does not risk it being committed.
- **FR-012**: The CDP-attach path (`HEADLESS_CDP_URL` set) MUST NOT read or write the state file
  under any circumstance; the Director's own Chrome manages its own sessions and this feature
  MUST NOT touch that browser's cookie jar in any way.
- **FR-013**: Every Chrome launch on the launched-profile path MUST pass the launch option that
  keeps Playwright from adding `--no-sandbox` to the Chrome command line.
- **FR-014**: Every other Chrome launch already present in the codebase (at minimum,
  `scripts/check_env.py`'s browser-reachability probe) MUST pass the same launch option, for the
  same reason, even where the launch is never seen by the Director.

### Non-Functional Requirements

- **NFR-001**: A cookie value MUST NOT appear in stdout, stderr, or any preview artifact
  (screenshot or JSON) at any point this feature introduces, extending the redaction guarantee
  `PATTERNS.md` already documents for every other typed or stored value in this codebase.
- **NFR-002**: The export step MUST NOT retry a failed write; it fails soft on the first attempt
  (FR-009) rather than looping, so a persistent write problem never delays a session's close by
  more than one attempt's worth of time.

### Key Entities

- **Session cookie state file**: the persisted artifact this feature introduces, one JSON file
  per profile directory, holding only the session cookies (no expiry) a browser context held at
  its most recent clean close. Not a new kind of secret store; it inherits the vault-grade
  status the profile directory already carries.
- **Session cookie entry**: one cookie record within the state file, carrying the fields a
  browser needs to restore it (name, value, domain, path, expiry marker, and its security-related
  flags). Never partially written; the file as a whole is replaced on every export.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a `probe <url> --apply` seed followed by a later `probe <url>` preview against
  a page that sets a cookie with no expiry through `document.cookie`, that cookie is present in
  the relaunched context, proven without a real login-protected site by an opt-in local test.
- **SC-002**: `--no-sandbox` is absent from the Chrome command line on 100% of launched-profile
  Chrome processes this codebase starts, including `scripts/check_env.py`'s probe.
- **SC-003**: The unit tests covering import, export, and the sandbox launch option run in under
  1 second combined, without opening a browser.
- **SC-004**: Every note-producing path this feature adds (state file missing and silent, state
  file unreadable, state file malformed, a rejected cookie entry, an export failure) has its own
  passing unit test using a fake context object, with no real browser involved.
- **SC-005**: Across every test this feature adds, zero test asserts on or is satisfied by a
  cookie name or value appearing in any captured output; every assertion about output content is
  a negative one (the value is absent).
- **SC-006**: In every test exercising the CDP-attach path, the import and export functions are
  never called and the state file is never created, read, or modified.
- **SC-007**: The opt-in browser test (`HEADLESS_TEST_BROWSER=1`) proves a session cookie set by
  `document.cookie` on a local fixture page survives a `Session` close and a fresh relaunch on the
  same profile directory, with no visible window and no request to any public network.

## Assumptions

- Chrome's own persistent-profile cookie jar already keeps a cookie that carries an expiry across
  a restart; this feature exists only to recover the class of cookie Chrome does not keep on its
  own (session cookies, no expiry), confirmed empirically by the orchestrator before this feature
  was scoped.
- `context.cookies()` (to read what a context currently holds) and `context.add_cookies()` (to
  hand cookies back to a fresh context) are the mechanisms the pinned Playwright version
  (1.62, per `MEMORY.md`) exposes for this; no other supported mechanism was found during root
  cause analysis.
- Passing the launch option that suppresses `--no-sandbox` is safe on the Director's machine: it
  was verified empirically that a Chrome launched this way starts normally and reads back a
  correct title and user agent.
- The profile directory's existing vault-grade classification (gitignored, never shared, outside
  the repository by default) already covers the state file this feature adds inside it; this
  feature does not need to invent new handling beyond the file mode and atomic-write guarantees
  in the Functional Requirements above.
- The Director is the only person who runs this tool; the state file's threat model is the same
  single-user local-machine model the rest of `CLAUDE.md`'s Secrets section already assumes.

## Out of Scope

- The CDP-attach path (`HEADLESS_CDP_URL`): explicitly untouched by this feature, per FR-012.
- Logins that live in `sessionStorage` rather than in a cookie (for example, a JWT kept in
  `sessionStorage`, as the India ITR e-filing portal is known to do): not persisted by this
  feature. A future feature could add this if a real errand needs it.
- Encrypting the state file beyond the operating system's own file permission bits: the profile
  directory already holds equivalent plaintext data (Chrome's own cookie database) at the same
  level of protection, so this feature does not raise the bar beyond matching it.
- Any new environment variable or CLI flag: the state file's location is derived, not
  configured, per FR-002.
- Recovering from a site's bot-defense-triggered logout automatically: the recovery path is the
  Director re-running `--apply` to seed the login again, unchanged from today.
