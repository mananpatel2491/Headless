# Tasks: Recorded-errand scaffolding (007-record-scaffold)

- [x] T001 `headless/record.py`: in-page observer (`INIT_SCRIPT`) with selector derivation,
      label capture, password flag, guarded registration, binding delivery.
- [x] T002 `headless/record.py`: `flatten_registry` mirroring `ProfileRegistry.get` in
      reverse (typed arrays, duplicate-`type` and untyped skips, empty-scalar drops) and
      exact-match `match_value`.
- [x] T003 `headless/record.py`: `WalkRecording` event rules - match-then-discard sources,
      checkbox/select kinds, password/OTP skips, terminal-click handoff and truncation,
      last-change-wins in place, nav dedupe, ordered unique `dependencies`.
- [x] T004 `headless/record.py`: value-free `to_walk_json`, `validate_errand_name`,
      `generate_draft` (compilable walk-framework errand, TODO and NOTE markers, skip notes,
      nav comments).
- [x] T005 `scripts/record.py`: CLI wiring, TTY/headed/CDP refusals, fail-soft match-table
      load, Session (PREVIEW + `show`) with binding and `framenavigated` handlers, post-Enter
      flush, artifact writes, value-free summary and promotion instructions.
- [x] T006 `tests/test_record.py`: unit suite per SC-001 (29 tests), including
      value-absence assertions on both artifacts and a compile-and-instantiate round trip of
      the generated draft.
- [x] T007 `tests/fixtures/record.html` + `tests/test_record_browser.py`: opt-in end-to-end
      fixture walk per SC-002, including the in-flight payload assertion that the
      allowlisted synthetic password value never leaves the page.
- [x] T008 Director-layer docs: `PATTERNS.md` entry, `Project_Structure.md` tables and
      changelog row, `Function_Mapping.md` scaffolding-tool note, `scripts/README.md`
      Maintenance row.
- [x] T009 Gates: full unit suite, opt-in browser suite, `verify_structure.py`,
      `scan_secrets.py --staged`.
- [ ] T010 Director UAT: one real recording on the Director's machine (a real site, the real
      profile), review of the generated draft, and a promoted-draft preview run.
