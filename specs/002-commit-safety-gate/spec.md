# Feature Specification: Commit Safety Gate

**Feature Branch**: `v0.0.2` (spec directory `002-commit-safety-gate`)

**Created**: 2026-08-24

**Status**: Draft

**Input**: User description: "The repository is now public. Ensure our future commits are
always credentials and PII safe: a local pre-commit scanner, a Claude Code write-time check,
and a CI backstop, all zero-install, plus an allowlist for known-safe test fixtures."

## Why

Headless became a public repository on 2026-08-24. Until now, a leaked credential or a piece
of the Director's personal data (a PAN, a phone number, a card number) reaching a commit was a
private embarrassment at worst. On a public repository it is a real exposure: anyone can read
every commit, including ones later amended or reverted, forever. The Director's instruction is
that every future commit stays credentials-and-PII safe. This feature adds one scanner, used at
three points in the path a change takes from an idea to public history (a local commit, an
assistant-written file, a pushed change), so a slip is caught as early as possible and, failing
that, no later than the moment it becomes visible to anyone else.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A commit is refused before it exists (Priority: P1)

The Director stages a change that includes a credential or a personal identifier and runs
`git commit`. The commit is refused before it is created: nothing enters the repository's
history, and the refusal names the file, the line, and the kind of finding without showing the
value itself. The Director fixes the line, or marks it as a known-safe exception, and commits
again.

**Why this priority**: A commit that never happens can never leak. Every later safeguard in
this feature is a backstop for the case where this one did not run or was bypassed.

**Independent Test**: Stage a file containing a synthetic credential and a synthetic personal
identifier, attempt to commit, and confirm no commit is created and the refusal names both
findings. Remove the findings, commit again, and confirm it succeeds.

**Acceptance Scenarios**:

1. **Given** a staged change containing a credential-shaped value, **When** the Director
   attempts to commit, **Then** the commit is refused before it is created, and the refusal
   names the file, the line, the kind of finding, and its severity, without reproducing the
   value.
2. **Given** a staged change containing a personal identifier (for example a card number that
   passes its checksum), **When** the Director attempts to commit, **Then** the commit is
   refused the same way.
3. **Given** staged changes containing neither a credential nor a personal identifier, **When**
   the Director commits, **Then** the commit proceeds with no delay perceptible to the
   Director.
4. **Given** a staged change that only removes a line that contained a credential, **When** the
   Director commits, **Then** the commit is not refused, because only added lines are examined.
5. **Given** a freshly cloned copy of the repository where the one-time local setup has not yet
   run, **When** the Director attempts to commit a secret, **Then** the local refusal does not
   fire, and the environment self-test reports plainly that the setup step is missing.

---

### User Story 2 - Claude Code cannot write the content to disk in the first place (Priority: P1)

Claude Code is about to write or edit a file in this repository and the new content contains a
credential or a personal identifier. The write is refused before any byte reaches disk, and the
reason given back to Claude Code names the finding, masked, so the assistant can correct its own
output and try again. A write with no such content proceeds with no visible delay and no
message.

**Why this priority**: Most of the content that ends up in this repository is now written by an
assistant, not typed by hand. Catching a slip before it reaches disk is earlier, and cheaper to
fix, than catching it at commit time, and it protects against content that a human never reviews
line by line before it is staged.

**Independent Test**: Ask Claude Code to write a file containing a synthetic credential and
confirm the write is refused and no such file, or no such content, exists afterward. Ask it to
write clean content and confirm the write proceeds normally.

**Acceptance Scenarios**:

1. **Given** Claude Code is about to write a new file whose content contains a credential-shaped
   value, **When** the write is attempted, **Then** it is refused before any bytes reach disk,
   and the reason given back to the assistant contains only a masked snippet of the finding.
2. **Given** Claude Code is about to edit an existing file by inserting a line containing a
   personal identifier, **When** the edit is attempted, **Then** it is refused the same way.
3. **Given** content with no credential or personal identifier, **When** Claude Code writes or
   edits it, **Then** the write proceeds with no visible delay and no message.
4. **Given** the write-time check is handed an input it cannot interpret (an unexpected shape,
   an unrelated tool, a malformed payload), **When** it runs, **Then** it allows the operation
   to proceed rather than blocking Claude Code's work; it never fails the assistant's turn
   because of its own confusion.

---

### User Story 3 - CI and GitHub catch anything that slipped (Priority: P2)

A change reaches the shared repository, whether it was pushed from a machine that had the local
refusal active or not. An automated check scans the change's complete history, not only its
latest snapshot, and fails if it finds a credential or a personal identifier anywhere in it.
GitHub's own secret scanning and push protection, already active on the repository, run
alongside it.

**Why this priority**: The local and write-time checks cover the ordinary path, but a Director
working from a machine without the local setup, a manual `git commit --no-verify`, or a
not-yet-covered assistant path are all realistic gaps. This is the backstop that does not depend
on any one machine being configured correctly, and it is what actually protects a public
repository if the earlier layers are ever skipped.

**Independent Test**: Push a branch whose history contains a synthetic credential in a commit
that is no longer in the latest snapshot (added then removed) and confirm the automated check
still fails, naming the finding. Push a clean branch and confirm the check passes.

**Acceptance Scenarios**:

1. **Given** a change is pushed to the shared repository, **When** the automated check runs,
   **Then** it scans the complete history reachable from that change, not only the latest
   snapshot, and fails if any secret or personal identifier is found anywhere in it.
2. **Given** a pull request is opened, **When** the automated checks run, **Then** both this
   project's own scan and GitHub's own secret scanning and push protection are active on the
   same change.
3. **Given** the automated check finds nothing, **When** it finishes, **Then** the change is
   reported clear, at no cost to the Director beyond the free allowance already in use for a
   public repository.

---

### User Story 4 - The Director allowlists a known-safe fixture (Priority: P3)

A handful of test fixtures already in the repository are deliberately shaped like real secrets
and personal identifiers, because they exist to prove the scanner catches those shapes. The
Director marks each one as a known-safe exception, either by listing it once for the whole
repository or by marking a single line in place, so it stops being flagged everywhere it is
used, without weakening detection of the same shape anywhere else.

**Why this priority**: Without this, the first commit of this very feature's own test suite
would refuse itself. It matters less than the three checks above only because, once the initial
allowlist is seeded, the Director rarely touches it again.

**Independent Test**: Add a synthetic fixture value to the allowlist, confirm every scan mode
stops flagging it, then confirm the same shape used somewhere else in the repository (not
allowlisted) is still flagged.

**Acceptance Scenarios**:

1. **Given** a test fixture in the repository intentionally resembles a real secret, **When**
   the Director adds it to the repository-wide allowlist, **Then** it stops being flagged on
   every scan mode, and an unrelated occurrence of the same shape elsewhere is still flagged.
2. **Given** a single line legitimately needs to contain a flagged-looking value, **When** the
   Director marks that line as an exception in place, **Then** only that line stops being
   flagged; the same value elsewhere in the file is still flagged.
3. **Given** the Director removes an allowlist entry, **When** the next scan runs, **Then** the
   previously exempted value is flagged again.

---

### Edge Cases

- A binary file happens to contain bytes that would match a pattern: it is skipped, because
  binary files are never scanned.
- A path already excluded from the repository's own history (the local disposable-artifacts
  folder, the Python environment folder, the version-control folder itself) is skipped by every
  scan mode.
- A file uses an encoding the scanner cannot cleanly read: the scan does not crash; it reports
  what it can and does not silently skip the whole file without saying so.
- The allowlist file contains a blank line or a comment: ignored, not treated as an entry.
- The same value would match more than one detection category (for example a string that is
  both a plausible token and a plausible identifier): every matching category is reported, not
  only the first.
- A very large set of staged changes, or a very long repository history, is scanned: the scan
  still completes within its stated time budget rather than appearing to hang.
- A masked finding's underlying value is very short: the mask still never reveals more of the
  value than the fixed tail the scanner always shows, regardless of the value's length.
- The write-time check runs for a tool that is not one that writes file content: it does nothing
  and never blocks that operation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide one scanner capable of examining, on request: only
  the added lines of a staged change, the complete content of one or more named files, every
  version of every file ever committed to the branch under review, and content an assistant is
  about to write to disk. The scanner MUST work using only what running the project already
  requires; it MUST NOT require installing any additional software.
- **FR-002**: When examining a staged change, the scanner MUST look only at lines being added,
  not at a file's full existing content, so that editing one line of an existing file does not
  force review of unrelated content already in that file.
- **FR-003**: When examining named files or committed history, the scanner MUST look at each
  version's complete content.
- **FR-004**: The scanner MUST detect, at minimum, these categories of committable secrets:
  cloud and platform access tokens (including GitHub, AWS, Google, Slack, and AI-provider
  tokens), session tokens shaped like a JWT, private-key material, and a generic
  password-or-API-key-or-token assignment to a quoted value of meaningful length.
- **FR-005**: The scanner MUST detect, at minimum, these categories of personal identifiers:
  Indian PAN and Aadhaar numbers, Indian and US phone numbers, email addresses, payment card
  numbers that pass a checksum validation, and bank account numbers in IBAN form.
- **FR-006**: The scanner MUST NOT report an email address at a documented example domain, a
  documented no-reply address, or a platform's own generated no-reply address as a finding.
- **FR-007**: Every finding the scanner reports MUST identify the file, the line, the kind of
  finding, and its severity, and MUST NOT reproduce the matched value; the value MUST appear
  only as a fixed mask plus its own last two characters.
- **FR-008**: The Director MUST be able to mark a specific known-safe value as an exception for
  the whole repository, or mark a single line in place as an exception, without disabling
  detection of the same pattern anywhere else.
- **FR-009**: A commit that would introduce a detected secret or personal identifier MUST be
  refused before the commit object is created; nothing beyond fixing the flagged line or
  allowlisting it MUST be required to proceed.
- **FR-010**: The local commit refusal MUST activate automatically on a repository clone once
  the Director has completed the one-time setup step documented for it, and MUST NOT require
  any action on every individual commit beyond that one-time step. The environment self-test
  MUST report whether that step has been completed.
- **FR-011**: Content an assistant is about to write to a file in this repository MUST be
  scanned before it reaches disk. A detected secret or personal identifier MUST cause the write
  to be refused, with the reason given back to the assistant containing only masked findings, so
  it can correct its own output and retry.
- **FR-012**: The write-time check MUST NOT prevent the assistant from working because of a
  malformed or unrecognized input; when it cannot make sense of what it was given, it MUST allow
  the operation to proceed rather than fail closed.
- **FR-013**: Every pushed change and every proposed change to the shared history MUST be
  scanned automatically before it is reviewable, independently of whether the local commit
  refusal ran on the machine that produced it, so that a secret committed without the local
  setup active is still caught.
- **FR-014**: The automatic check in FR-013 MUST run at no cost to the Director, using the free
  allowance already available to a public repository, and MUST run alongside the repository
  host's own secret-scanning and push-protection controls rather than replacing them.
- **FR-015**: Binary files and paths already excluded from the repository's own version-control
  review MUST be skipped by every scan mode.
- **FR-016**: Every detection category MUST be provable, without a live secret ever being
  required, on a synthetic sample known to trigger it and known to stop triggering it once that
  sample is allowlisted.
- **FR-017**: The existence, activation state, and one-time setup step of the commit safety gate
  MUST be documented in the same places the Director already reads the project's operating
  rules, and kept current in the same change that introduces or changes the gate.

### Key Entities

- **Pattern**: one named, categorized rule the scanner looks for (a credential shape or a
  personal-identifier shape), carrying a severity.
- **Finding**: one match of a Pattern against a specific location (file and line, or a piece of
  content an assistant is about to write); always reported masked, never with its raw value.
- **Allowlist entry**: a Director-declared exception, either a known-safe value good for the
  whole repository or a marker on a single line, that suppresses a Finding without disabling its
  Pattern elsewhere.
- **Scan mode**: which of the four examination modes (staged change, named files, full history,
  content an assistant is about to write) a given run uses; determines what is examined, not
  what is detected.
- **Hook input**: the description of one write-in-progress that the write-time check receives
  and must classify as clean, refused, or not applicable to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of synthetic samples representing each detection category are flagged before
  allowlisting, and 0% are flagged after their sample is allowlisted, across every scan mode.
- **SC-002**: Every attempt to commit a staged change containing a synthetic credential or
  personal identifier is refused, with zero commits created, on a repository with the one-time
  setup completed.
- **SC-003**: Every attempt to write content containing a synthetic credential or personal
  identifier through the assistant is refused before any bytes reach disk.
- **SC-004**: Across a corpus of clean content (no credential or identifier), 0% is refused for
  that reason, at either the commit or the write-time check.
- **SC-005**: No finding's underlying value appears in any output the scanner produces, in any
  scan mode, verified by searching that output for the raw values used in the proof corpus.
- **SC-006**: A full scan of the repository's tracked working content completes in under 2
  seconds, so it adds no perceptible delay to an ordinary commit.
- **SC-007**: A change that reaches the shared repository without the local refusal having run
  is still flagged by the automated backstop before the change is reviewable, at no cost beyond
  the free allowance already in use.
- **SC-008**: A newly allowlisted known-safe sample stops being flagged on the very next scan,
  with no measurable change in how quickly an unrelated, non-allowlisted finding of the same
  category is still caught.

## Assumptions

- The repository's host-level secret scanning and push protection were already turned on when
  the repository went public (2026-08-24); this feature adds the project's own layered scanner
  around that existing control and does not configure the host-level control itself.
- No local secret-scanning tool is installed on the Director's machine; this feature does not
  require installing one, only using what the project already needs to run.
- The repository is public and hosted the way this one already is, so the automated backstop
  runs at no cost.
- A handful of existing test fixtures intentionally resemble real secrets and personal
  identifiers and are allowlisted as part of delivering this feature, not discovered later as a
  surprise gate failure.
- The Director is the only person who commits to this repository or configures Claude Code
  against it; the write-time check protects the Director's own assistant-written content, not a
  multi-user population of contributors.
- The one-time local setup step needed to activate the commit refusal is a single documented
  command run once per clone; a clone where it has not been run still benefits from the
  write-time check and the automated backstop, just not the local commit refusal.
- Rewriting existing repository history, scanning the local browser profile or its preview
  artifacts, adopting a paid third-party scanning service, and organization-wide policy controls
  are all out of scope for this feature.
