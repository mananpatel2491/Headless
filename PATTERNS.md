# Pattern Registry: Headless

This document records established engineering patterns and design decisions so that later
sessions inherit them instead of re-litigating them. Every entry reflects the actual codebase.

## 1. Architectural Patterns

- **Thin package, one script per errand** (inherited from the Director's Atlassian toolkit).
  Reusable mechanics live in `headless/` (config, browser session, secrets, profile, gates,
  preview). Each errand is one runnable `scripts/<errand>.py` that composes them. Extend the
  package; never re-implement browser or secrets plumbing inside a script.
- **Preview-by-default, `--apply` to act, human handoff at the terminal step.** Scripts share
  the gate helpers in `headless/gates.py`. The three modes are `preview` (default, no site
  writes), `apply` (fills up to the declared handoff point), and `check` (read-only selector
  probe). There is no submit mode by design; see `CLAUDE.md`.
- **Registry is the only writable source.** The profile registry (`headless/profile.py`) is
  the sole source of values a script may type, alongside the vault and hand-authored literals
  (`headless/fields.py`'s `Source`). Field mappings are hand-authored dicts inside the errand
  script, reviewed in the preview before `--apply`.
- **`Session.fill` is the only sanctioned way to type; `Session.page` is exposed for reads
  (v0.0.1).** A structural test (`tests/test_no_direct_typing.py`) parses `scripts/*.py` with `ast` and
  refuses any direct `.fill(`, `.type(`, `.press(`, `.click(`, `.select_option(`, or `.check(`
  call on a page or locator, so an errand cannot type outside the registry/vault/literal path
  without failing the commit gate. This replaces an earlier, weaker claim ("derived or
  LLM-produced values are structurally unwritable") that described only the `FieldPlan`/`Source`
  type shape, not an enforced boundary; the mechanical scan is the actual enforcement.
- **Secrets backend seam.** `headless/secrets.py` exposes `get_secret(name)` over a backend
  chosen by `HEADLESS_SECRETS_BACKEND`: `keychain` (macOS `security` CLI, default) or `gcp`
  (Secret Manager, lazy import, only when configured). Scripts never read `.env` for secrets;
  `.env` holds non-secret configuration only.
- **Persistent Chrome profile.** `headless/session.py` launches the installed Chrome
  (`channel="chrome"`) with `launch_persistent_context` on `HEADLESS_PROFILE_DIR`, or attaches
  over CDP when `HEADLESS_CDP_URL` is set. Logins are seeded by the Director in that window
  and survive between runs. Reads retry; writes never retry.
- **Quiet by default (v0.0.1, Director decision 2026-08-24).** Two independent `Config` axes:
  `headed` (can a real windowed Chrome process be produced at all - `HEADLESS_HEADED`,
  `--headless`, unchanged in meaning) and `show` (is the window visible from launch -
  `HEADLESS_SHOW`, `--show`, new, default `False`). `headless/session.py`'s
  `_effective_headed(mode, config)` decouples the two: preview/check ignore `config.headed`
  entirely and launch invisible (Chrome's own headless mode) unless `show` is set, regardless
  of `HEADLESS_HEADED`; apply always launches a real window (`config.headed`, gated as before
  by `resolve_mode`) but, unless `show`, hides it immediately after launch
  (`Session._hide_window`, called only on the launched - never the CDP-attach - path so the
  Director's own browser window is never touched) and restores it (`_restore_window`) only at
  `handoff()`, right before printing "Your turn". `--headless` and `--show` are mutually
  exclusive CLI flags; `--headless` with `--apply` is still refused (unchanged: the handoff
  needs a window). Empirically verified on this machine (macOS, Chrome 151, no Accessibility
  permission granted to this automated session) that hiding is imperfect: CDP's
  `Browser.setWindowBounds({"windowState": "minimized"})` never took effect (the window kept
  reporting - and staying - `"normal"`); the `--start-minimized` and
  `--window-position=-32000,-32000` launch args were both silently ignored; `osascript`/System
  Events native minimize failed with "not allowed assistive access" (-1719, needs an
  interactive one-time Accessibility grant this session cannot make). What DID have a partial
  effect: a post-launch `Browser.setWindowBounds` position move - macOS clamps it so some
  minimum sliver stays reachable, smallest pushing towards the bottom-right of the screen on
  this display (roughly a 40x131 point corner sliver, versus ~258 points or more pushing
  left/up). `_hide_window` therefore does both (attempts the CDP minimize, harmless if
  ineffective and may work on another machine/Chrome version, then pushes towards that corner)
  and is explicitly documented as best-effort, not a hard guarantee of zero visible pixels; a
  future session with Accessibility permissions granted could add a real `osascript` minimize
  as a strictly better mechanism. Restore uses explicit on-screen `left`/`top` plus
  `page.bring_to_front()`. **Correction to an assumption used to draft this feature**: this
  Chrome (channel `chrome`, v151, launched `headless=True` via Playwright, both with and
  without an explicit `--headless=new` arg) DOES report `HeadlessChrome` in
  `navigator.userAgent` (verified 2026-08-24) - the "new headless mode drops HeadlessChrome
  from the UA" claim does not hold here. Anti-bot fingerprinting of headless Chrome (by UA or
  otherwise) is a real, unresolved risk for real errands; `--show` (or `--check` first, to see
  what a site does before committing to headless preview) is the escape hatch.
- **CDP attach never touches the Director's own tabs (v0.0.1, FIX-FIRST 5).** On the CDP
  path, `Session.__enter__` always opens a brand-new page (`context.new_page()`), never
  reusing `context.pages[0]` - an attached context may already hold the Director's own
  actively-used tabs. `__exit__` closes only that page, then calls `browser.close()` to
  disconnect. Verified live 2026-08-24 (this machine): attaching to a real Chrome started
  with `--remote-debugging-port`, using it, and exiting the `Session` leaves the original
  Chrome process running and its pre-existing tab untouched; `browser.close()` on a
  CDP-attached `Browser` disconnects the client, it does not terminate the real Chrome
  process. The launched (persistent-profile) path is unaffected: it owns the whole browser
  process and closes the context normally. Attaching is not a privacy boundary the same way
  the persistent profile is, though: when attaching over CDP (`HEADLESS_CDP_URL`), attach only
  to a Chrome started for Headless - the attached context carries every session that browser
  holds.
- **Screenshots are masked, not redacted (v0.0.1).**
  `headless/preview.py` writes `<errand>-<UTC timestamp>.png` and `.json` under
  `HEADLESS_PREVIEW_DIR` (default `<repo root>/previews`, gitignored). The JSON's `fields`
  pass through `PreviewRecord.__post_init__`'s redaction (secrets/registry values masked to
  `****` plus the last two characters; literals shown as-is) before the record exists in any
  other form. The `.png` is different: `Session.screenshot()` injects a `<style>` tag
  (`-webkit-text-security: disc` on `input`/`textarea`/`[contenteditable]`; transparent text
  on `select`) right before capturing, then removes it, so a just-typed secret or registry
  value is not legible as text in the image - but this is a *visual mask*, not redaction, and
  page-rendered data the mask cannot reach (e.g. a logged-in portal displaying the Director's
  own name) can still appear. The mask preserves length (one disc per character), so a
  screenshot still discloses how long a typed value is. If the page's own CSP (e.g.
  `style-src 'self'`) refuses the mask's inline `<style>` injection, `screenshot()` never
  falls back to capturing unmasked: it returns `None` (same as `--no-screenshot`, JSON-only)
  and prints one note (`note: screenshot skipped, the page's CSP blocked the mask`).
  `--no-screenshot` / `HEADLESS_SCREENSHOTS=0` (`Config.screenshots`, default `True`) skips the
  screenshot entirely and writes only the JSON. Because of the screenshot's weaker guarantee,
  `previews/` as a whole is vault-grade local data: gitignored, never shared or attached
  anywhere, disposable. See `CLAUDE.md`'s Secrets section for the same reasoning spelled out
  for the Director.
- **Cross-Platform Automation (AVF).** Maintenance and errand scripts are Python with
  `argparse`; Spec Kit helper scripts are the Python variant (`.specify/scripts/python/`).
- **Automation-First CLI (AVF).** Every script runs non-interactively with flags
  (`--apply`, `--check`, `--profile-dir`, `--headless`) so it can run from cron or CI, and
  every action-taking path has a safe preview.
- **Proactive Hardening (AVF).** When touching an existing file, audit it for leaked secrets,
  injection through page content, and resource leaks (unclosed browser contexts); patch
  immediately.
- **Spec-Driven Feature Workflow (Spec Kit).** Features beyond trivial fixes run
  `specify -> clarify -> plan -> tasks -> implement` and leave durable artifacts in
  `specs/NNN-slug/`. `.specify/memory/constitution.md` is always a distillation of
  `CLAUDE.md` plus this file, with an explicit precedence header; it never introduces new
  rules.
- **Lazy registry loading (v0.0.1).** `headless/errand.py`'s `Errand.run()` never calls
  `ProfileRegistry.load(vault)` eagerly; it hands `plan()` a lazy wrapper that only
  fetches the `profile` vault item on the first `.get()` call a `FieldPlan` actually
  triggers. A read-only errand with an empty plan (`probe.py`) therefore never needs a
  `profile` vault item to exist. Apply mode still pre-resolves every planned source
  (which may trigger the lazy load) before any browser window opens.
- **check_env's "browser" row launches, briefly, headless (v0.0.1).** Playwright's
  Python API has no public way to resolve a `channel="chrome"` executable path without
  starting it (only `chromium.executable_path` for the bundled, non-channel browser).
  `scripts/check_env.py` proves Chrome is reachable by launching it with `headless=True`
  and closing it immediately; this does not violate "check_env opens no window" because
  no visible window is created (the headed/headless distinction used throughout this
  repo is about visibility, not process existence).

## 2. Coding Standards

- `argparse` for every script; a module docstring that states the errand's background, the
  site, the handoff point, and the secrets it needs.
- Type hints and `from __future__ import annotations` throughout `headless/`.
- Tests under `tests/` with `pytest`; pure logic (mapping, gates, redaction, config parsing)
  is unit-tested without a browser. Browser paths are exercised by `--check`.

## 3. Tooling Conventions

- **Commit gate**: `python -m pytest -q` and `python scripts/verify_structure.py` both pass.
  Exception string (must appear verbatim in the commit message):
  `I understand the Headless validation gate is failing and I allow the exception to have the code committed to the repo`.
- **Hyphens only**: no em or en dashes in any file (global PreToolUse hook denies the write).
- **Version branches**: `vX.Y.Z` in a worktree under `../worktrees/Headless/`, `merge --no-ff`
  into `main`; `CHANGELOG` lives in the `Project_Structure.md` Changelog table.
- **Previews are disposable**: `previews/` is gitignored; delete freely.
- **Chrome profile-lock error text (v0.0.1, this machine, 2026-08-24)**: a second
  `launch_persistent_context` on a profile directory already held by another Chrome
  instance raises a Playwright `Error` whose message contains
  `Failed to create a ProcessSingleton for your profile directory` and
  `SingletonLock: File exists`. `headless/session.py` matches on these substrings to
  turn it into the "profile in use" `GateRefused` the edge cases call for, instead of a
  raw stack trace.
- **Benign Playwright sync-API teardown warning**: a clean `with sync_playwright() as p:`
  run (used by `headless/session.py` and `scripts/check_env.py`'s browser/playwright
  rows) can still print `Task was destroyed but it is pending!` /
  `TargetClosedError: Target page, context or browser has been closed` to stderr after
  the process's real work is done and the exit code is correct. This is a known
  cosmetic race in Playwright's sync wrapper, not a Headless bug; do not chase it.
- **`security add-generic-password` has no stdin path for a value (v0.0.1, FIX-FIRST 13)**:
  `-w <value>` is the only interface it offers, so during `KeychainBackend.put_secret`'s
  call the value is a real argv element of the child process, visible to local tools that
  can read another process's argv (`ps -ww`) for that brief window. Accepted for a
  single-user Mac Headless already trusts with the Keychain itself; the `profile` item is
  meant to be seeded by hand, not written by an unattended errand. A failed `security` call
  (non-zero exit) is never silently ignored: `put_secret`/`delete_secret` raise
  `RuntimeError(f"keychain write failed for item {name!r} (security exit {exc.returncode})")`
  from the caught `subprocess.CalledProcessError`, `from None` so the original (whose `.cmd`
  holds the raw value) is never chained onto the traceback.
- **`GcpBackend` detects `NotFound` by exception class name, not `isinstance`**: it never
  imports `google.api_core.exceptions` (that would defeat the lazy-import guarantee for a
  package that is deliberately not installed here). `get_secret`/`put_secret` check
  `type(exc).__name__ == "NotFound"` instead, which matches both the real SDK's exception
  (named `NotFound`) and a test double of the same name with no import required.
