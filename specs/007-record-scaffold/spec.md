# Feature Specification: Recorded-errand scaffolding

**Feature branch**: `v0.0.7` | **Spec**: 007-record-scaffold | **Status**: Implemented, Director UAT pending

## Problem

Every errand so far was hand-written: read the site, derive selectors, map fields to registry
paths, place the handoff. That authoring cost is the scaling bottleneck of "one gated script
per task" - each new errand is an afternoon before its first preview run. The Director already
performs each errand by hand at least once (seeding logins, checking a funnel); that walk
contains almost everything the script needs.

## Proposal

A maintenance script, `scripts/record.py <URL> <errand-name>`, that opens a visible window on
the Headless profile, lets the Director perform the errand by hand once, observes the walk
structurally, and scaffolds two artifacts under the gitignored `previews/recordings/`: a
value-free walk record (JSON) and a draft walk-framework errand script. The Director reviews
the draft (selectors, sources, handoff text), promotes it to `scripts/` by hand, and adds its
`Function_Mapping.md` row in the same commit. Authoring a new errand becomes review instead of
transcription; every existing gate is untouched.

## Functional requirements

- **FR-001**: The recorder never drives the page. It calls neither `Session.fill` nor
  `Session.click`, types nothing, clicks nothing, and adds no mode to `headless/gates.py`.
  The Director's own hands perform every site interaction during recording.
- **FR-002**: Observation is an injected, context-wide init script plus one exposed binding,
  re-armed on every navigation, guarded against double-registration, and wrapped so an
  observer fault can never break the page being driven.
- **FR-003**: A recorded event carries structural facts only: a derived selector (unique
  `#id`, then `data-testid`, then `tag[name]`, then `aria-label`, then a short
  `nth-of-type` path), tag, input type, label text (truncated), and flags. Button captions
  and labels are truncated to 60 characters.
- **FR-004**: A typed value exists in Python only inside `WalkRecording.add_event`, long
  enough to be compared against the flattened profile registry. Persisted artifacts hold the
  outcome only: `registry:<dotted.path>` on a match (further matching paths listed as
  alternatives, paths only), or a `literal:` placeholder plus a TODO marker on a miss.
- **FR-005**: A password field's value never reaches Python: the init script sends a flag and
  an empty value. The control is recorded as skipped (selector and reason only).
- **FR-006**: An OTP-looking control (autocomplete `one-time-code`, or a name/id/label hint
  matching the OTP pattern) is skipped the same way as a password field.
- **FR-007**: A click on a terminal-looking control (pay, purchase, buy, checkout, place
  order, submit, confirm, verify, e-verify, OTP, one-time) is never recorded as a step: it
  sets the draft's `HANDOFF`, ends the recording, and every later event is ignored. The
  pattern is deliberately over-broad - a false positive costs one hand-written `ClickStep`
  in review; a false negative would scaffold a click the framework must never perform.
- **FR-008**: Registry matching mirrors `ProfileRegistry.get`'s addressing in reverse,
  type-discriminated arrays included: an element without a scalar `type` is unaddressable and
  produces no match pair; a `type` shared by two elements produces none for either (the
  forward path would raise `RegistryAmbiguous`). Empty-string scalars produce no pair.
- **FR-009**: Registry matching is optional and fail-soft: `--no-registry`, a missing vault,
  a missing `profile` item, or malformed profile JSON each collapse to one value-free note
  and a fully-TODO draft. The recorder must work on a machine whose vault is not seeded yet.
- **FR-010**: The generated draft is an ordinary walk-framework `Errand` subclass: preview by
  default, `--check` probes its recorded selectors (`dependencies`), `--apply` fills up to
  its `HANDOFF`. It compiles as generated, contains no typed value, and marks every
  unresolved source with a TODO comment plus a head-of-file NOTE.
- **FR-011**: Both artifacts land under `previews/recordings/` (inside the already-gitignored,
  vault-grade `previews/` tree), never in `scripts/`. Promotion is a deliberate hand move.
- **FR-012**: Recording is refused without an interactive terminal, without a headed browser,
  and on the CDP-attach path (the observer must never be injected into the Director's own
  browser context). Refusals print `REFUSED: <reason>` and exit 1, mirroring errand
  conventions.
- **FR-013**: A browser-phase failure never loses the walk gathered so far: the artifacts are
  written from whatever was recorded, with one value-free note naming only the exception
  class.

## Success criteria

- **SC-001**: Unit tests cover every rule above without a browser (the event shapes are fed
  directly), including that a recorded raw value appears in neither the JSON artifact nor the
  draft, and that the draft compiles and instantiates into a real `Errand` whose walk matches
  the recording.
- **SC-002**: An opt-in browser test (`HEADLESS_TEST_BROWSER=1`) drives the local fixture
  `tests/fixtures/record.html` end to end and proves: selector derivation, label capture,
  registry match, TODO fallback, password and OTP skip (asserting the allowlisted synthetic
  password value never appears in any delivered payload), terminal-click handoff, and
  post-terminal event suppression.
- **SC-003**: The default commit gate (`pytest -q`, `verify_structure.py`,
  `scan_secrets.py --staged`) stays green with no browser installed beyond what the existing
  suite already needs.

## Out of scope

- Recording inside iframes, shadow DOM, drag interactions, file uploads, or contenteditable
  regions (the observer covers input/textarea/select and clickable controls).
- Auto-promotion of a draft into `scripts/` or auto-editing of `Function_Mapping.md` - review
  is the point.
- Any change to gates, session, fields, steps, or the errand state machine.
