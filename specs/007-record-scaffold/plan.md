# Implementation Plan: Recorded-errand scaffolding (007-record-scaffold)

## Design decisions

- **D1 - Pure-logic module, thin script.** `headless/record.py` holds everything testable
  without a browser (the init-script constant, event-to-step rules, registry flattening and
  matching, artifact and draft generation) and imports no Playwright. `scripts/record.py` is
  wiring: argparse, config, vault, `Session`, the binding, artifact writes. Mirrors the
  thin-package pattern every other feature follows.
- **D2 - Reuse Session in PREVIEW mode with `show` forced.** Recording needs a visible window
  the Director drives, login persistence, and the profile lock - all of which `Session`
  already provides. PREVIEW mode keeps `fill`/`click` refused by the existing gates, which is
  exactly the recorder's own contract (FR-001). No new mode, no session changes.
- **D3 - Context-wide init script plus one exposed binding.** `add_init_script` re-arms the
  observer on every navigation; `expose_binding` survives navigation and delivers events
  even while the main thread is blocked on `input()` (queued, then dispatched during the
  post-Enter flush calls). In-page buffering was rejected: a buffer dies with each
  navigation, and multi-page walks are the ones worth recording.
- **D4 - Match-then-discard is the value boundary.** One place in Python ever holds a typed
  value (`WalkRecording.add_event`), and its only output is a source reference or a
  placeholder. The password value never even reaches that point - excluded in-page - because
  a value the process never receives cannot leak, whatever later code does.
- **D5 - Terminal detection by visible caption, over-broad on purpose.** The constitution's
  terminal-action list, as a case-insensitive word pattern over the clicked control's own
  caption. Asymmetric costs decide ties: a false positive is one hand-written `ClickStep`
  during review; a false negative is a scaffolded forbidden click.
- **D6 - Drafts land in `previews/recordings/`, not `scripts/`.** Generated code must pass
  through the Director's review and the ordinary commit gates (`test_no_direct_typing.py`
  included) on its way into the repository - so the generator writes to vault-grade,
  gitignored ground and promotion stays a hand move.
- **D7 - CDP-attach refusal.** An attached context is the Director's own browser; injecting
  an observer there would record tabs Headless must never touch. Launched-profile path only.

## Files

- `headless/record.py` - NEW: `INIT_SCRIPT`, `TERMINAL_TEXT_RE`, `OTP_HINT_RE`,
  `RecordedField`/`RecordedClick`/`RecordedNav`/`SkippedField`, `flatten_registry`,
  `match_value`, `WalkRecording`, `to_walk_json`, `validate_errand_name`, `generate_draft`,
  `utc_timestamp`.
- `scripts/record.py` - NEW: CLI, gates, fail-soft match-table load, Session wiring, binding
  and `framenavigated` handlers, flush, artifact writes, promotion instructions.
- `tests/test_record.py` - NEW: unit coverage per SC-001.
- `tests/test_record_browser.py`, `tests/fixtures/record.html` - NEW: opt-in end-to-end proof
  per SC-002.
- `PATTERNS.md`, `Project_Structure.md`, `Function_Mapping.md`, `scripts/README.md` - the
  Director-layer updates the constitution requires in the same delivery.
