"""The headed persistent-profile Chrome session.

Launches the installed Chrome (`channel="chrome"`) on `config.profile_dir` via
`launch_persistent_context`, or attaches to a running Chrome over CDP when
`config.cdp_url` is set (D1, D2). Reads (`goto`, `probe`) retry once on a
transient error; writes (`fill`) never retry. `fill` is the only sanctioned
way to type into a page and accepts only a `FieldPlan`: it resolves the value
itself, at call time, through `fields.resolve_source` (D7) and is refused
outside apply mode. `page` is exposed for reads (goto/probe/screenshot use
it), never for typing.

CDP attach never touches the Director's own tabs: `__enter__` always opens a
brand-new page on the attached context (never reuses `context.pages[0]`,
which may be a tab the Director is actively using), and `__exit__` closes
only that page and disconnects (`browser.close()` on a CDP-attached `Browser`
disconnects the client; it does not terminate the Director's real Chrome
process. Verified 2026-08-24; see PATTERNS.md). The launched (persistent
profile) path owns the whole browser process and closes the context normally.

Quiet by default (v0.0.1, Director decision 2026-08-24): `Config.headed` and
`Config.show` are independent axes. Preview and check launch invisibly
(Chrome's own headless mode) unless `show`, regardless of `Config.headed`.
Apply always launches a real windowed Chrome (the handoff needs one) but,
unless `show`, hides that window immediately after launch and surfaces it
(restored, brought to front, focused) only at `handoff()` - never on the
CDP-attach path, which reuses the Director's own browser window and must
never be minimized or moved out from under them. See `_hide_window` for what
"hides" actually means on this machine.

Every screenshot masks form-control text first (a `<style>` tag using
`-webkit-text-security`/transparent-select-text, removed immediately after)
so a typed secret or registry value is not legible in the PNG; this is a
visual mask, not redaction, and page-rendered data (e.g. a logged-in
portal's display name) can still appear. See CLAUDE.md's Secrets section for
why `previews/` is still vault-grade local data. If the page's own
Content-Security-Policy blocks the mask's `<style>` injection,
`screenshot()` never falls back to capturing unmasked: it returns `None`
(JSON-only artifact, the same as `--no-screenshot`) and prints one note.

Session cookie persistence (v0.0.3, spec 003-login-persistence): Chrome drops
any cookie with no expiry (a session cookie - what most logins actually set)
on every `launch_persistent_context` restart, even though a cookie with an
expiry survives on its own. On the launched-profile path only,
`__enter__` imports `<profile_dir>/session-cookies.json` (if present) into
the fresh context before any navigation, and `__exit__` exports the
context's current session-only cookies to that file before closing. The
CDP-attach path never reads or writes this file (D1, FR-012). See
specs/003-login-persistence/data-model.md and contracts/session-state.md.
Every Chrome process this codebase launches also passes
`chromium_sandbox=True` (D7): Playwright adds `--no-sandbox` to every launch
unless this exact option is passed, which is what produced the "unsupported
command-line flag" warning bar the Director saw at the apply handoff.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Playwright, sync_playwright

from headless.config import Config
from headless.fields import FieldPlan, redact, resolve_source
from headless.gates import GateRefused, Mode
from headless.profile import ProfileRegistry
from headless.secrets import VaultBackend

# Substrings observed (2026-08-24, this machine) in the Playwright error raised
# by launch_persistent_context when a Chrome instance already holds the
# profile directory's lock. See PATTERNS.md.
_PROFILE_LOCK_HINTS = ("ProcessSingleton", "SingletonLock", "already in use")

# Masks typed text in form controls before a screenshot is taken (BLOCK 2a).
# input/textarea/[contenteditable]: disc-masked like a password field
# (verified in this Chrome: -webkit-text-security also computes and renders
# on a contenteditable element, not just <input>/<textarea>). select: the
# chosen option's visible text painted transparent (no reliable CSS "mask"
# for <select> rendering across platforms, so hiding the glyphs is the
# closest equivalent). This is a *visual* mask only; see the module
# docstring - it preserves length (one disc per character), so a screenshot
# still discloses how long a typed value is.
_SCREENSHOT_MASK_CSS = (
    "input, textarea, [contenteditable] { -webkit-text-security: disc !important; } "
    "select { color: transparent !important; text-shadow: none !important; }"
)

# Quiet-apply window hiding (v0.0.1, Director decision 2026-08-24). Verified
# empirically on this machine (macOS, Chrome 151): none of CDP's
# `windowState: "minimized"`, the `--start-minimized` launch arg, or the
# `--window-position=-32000,-32000` launch arg have any effect - the window
# always reports (and stays) `windowState: "normal"` at its default position.
# `osascript`/System Events native minimize is blocked here by missing
# Accessibility permissions (a one-time, interactive macOS grant this
# automated session cannot make). What DOES have a partial effect: a
# post-launch `Browser.setWindowBounds` position move - macOS's window
# manager clamps it so some minimum sliver stays reachable, and that sliver
# is smallest pushing towards the bottom-right (pushing left/up leaves far
# more of the window on-screen than pushing right/down on this display). So
# the best achievable result here is "small corner sliver", not "fully
# invisible"; record any different finding on another machine in PATTERNS.md
# rather than trusting this comment to still be accurate there.
_OFFSCREEN_LEFT = 32000
_OFFSCREEN_TOP = 32000
_RESTORE_LEFT = 100
_RESTORE_TOP = 100

# Session cookie persistence (v0.0.3, spec 003-login-persistence). The state
# file's location is derived from the profile directory already in use, not
# configured (FR-002, D2). See specs/003-login-persistence/data-model.md for
# the file's exact shape and invariants.
SESSION_COOKIE_FILENAME = "session-cookies.json"


def _session_cookie_path(profile_dir: Path) -> Path:
    """Where the launched-profile path's session-cookie state file lives for
    a given profile directory. See specs/003-login-persistence/data-model.md."""
    return Path(profile_dir) / SESSION_COOKIE_FILENAME


def _import_session_cookies(context, profile_dir: Path) -> bool:
    """Restore previously exported session cookies into a freshly launched
    context, before any navigation (D3). A missing state file is the
    expected shape of a fresh or never-seeded profile and prints nothing
    (FR-006). Every other failure - unreadable, malformed, empty, or
    `context.add_cookies()` itself rejecting the whole call - collapses to
    exactly one note naming only the exception's class, never its message
    (which could quote back a fragment of the untrusted file content) and
    never the file's contents (D4, FR-007, FR-008, FR-010). The run always
    proceeds with a usable context, imported or not.

    Returns True when there was nothing to import (no file) or the import
    succeeded, and False only when a file existed but the import failed.
    The caller uses this to decide whether `__exit__` may export at all: a
    failed import must never let the unconditional export that follows
    overwrite a good, previously exported file with an empty one (verifier
    FIX-FIRST 1, 2026-08-25).
    """
    path = _session_cookie_path(profile_dir)
    if not path.exists():
        return True
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            raise ValueError("session cookie state file is not a JSON array")
        context.add_cookies(entries)
        return True
    except Exception as exc:
        print(f"note: session cookies not restored ({type(exc).__name__})")
        return False


def _export_session_cookies(context, profile_dir: Path) -> None:
    """Export the context's current session-only cookies (`expires == -1`;
    Chrome's own persistent profile already keeps anything with a real
    expiry, D3) before the context closes. Every export replaces the state
    file's entire previous content (D3/D4 self-healing: a cookie the site
    has since cleared is simply absent from the new file) via a temp file in
    the same directory plus an atomic `os.replace`, and always leaves the
    file at mode `0600` (FR-005). Never retries on failure (NFR-002): a
    write problem collapses to exactly one note and the caller still
    proceeds to close the context (D4, FR-009).
    """
    profile_dir = Path(profile_dir)
    target = _session_cookie_path(profile_dir)
    tmp_path = profile_dir / f"{SESSION_COOKIE_FILENAME}.tmp"
    try:
        cookies = context.cookies()
        session_only = [c for c in cookies if c.get("expires") == -1]
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(session_only, f)
        os.chmod(str(tmp_path), 0o600)
        os.replace(str(tmp_path), str(target))
    except Exception as exc:
        # Best-effort cleanup: a failure anywhere between the temp write and
        # the atomic replace must never leave a plaintext-cookie temp file
        # behind (verifier FIX-FIRST 2, 2026-08-25). This cleanup itself can
        # never raise: a second failure here still must not break the run.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"note: session cookies not saved ({type(exc).__name__})")


def _effective_headed(mode: Mode, config: Config) -> bool:
    """What to actually pass as Playwright's `headless=` (negated) for this
    run. Apply always wants `config.headed` as resolved (True for every real
    run - the gate already refused otherwise; a test may pass False with
    `allow_headless_apply_for_tests=True` for a fast invisible-Chromium
    apply test, and that must still launch invisible). Preview and check
    ignore `config.headed` entirely and use `config.show` instead - the
    "quiet by default" design point: HEADLESS_HEADED no longer makes preview
    or check visible, only --show does, and `--headless` (headed=False) always
    wins over HEADLESS_SHOW=1 so an invisible run can be forced from the CLI.
    """
    if mode is Mode.APPLY:
        return config.headed
    return config.headed and config.show


def _should_hide_window(mode: Mode, config: Config) -> bool:
    """Whether `__enter__` should call `_hide_window()` after a launched
    (non-CDP-attach) headed window: apply only, and only without `--show`.
    Preview/check never hide - they are either invisible from launch
    (headless=True) or fully visible via --show; neither has a handoff to
    restore at."""
    return mode is Mode.APPLY and _effective_headed(mode, config) and not config.show


class FillFailed(RuntimeError):
    """Session.fill's locator action (fill/select_option/check) raised.

    The message is built from FieldPlan metadata and a redacted value only
    (never the underlying Playwright exception's message or the exception
    object itself, which can embed the raw value being typed in its call
    log). The original exception is deliberately not chained (`from None`).
    """

    def __init__(self, plan: FieldPlan, value: str, cause: BaseException) -> None:
        self.plan_name = plan.name
        self.selector = plan.selector
        self.kind = plan.kind
        self.cause_class = type(cause).__name__
        message = (
            f"fill failed for {plan.name!r} ({plan.selector!r}, kind={plan.kind!r}): "
            f"value={redact(value)!r}, cause={self.cause_class}"
        )
        super().__init__(message)


class Session:
    def __init__(
        self,
        config: Config,
        mode: Mode,
        *,
        confirm=input,
        allow_headless_apply_for_tests: bool = False,
    ) -> None:
        if mode is Mode.APPLY and not config.headed and not allow_headless_apply_for_tests:
            raise GateRefused("apply needs a visible browser")
        self.config = config
        self.mode = mode
        self._confirm = confirm
        self._playwright: Playwright | None = None
        self._browser = None  # set only on the CDP-attach path
        self.context = None
        self.page = None
        self._quiet_cdp = None  # set only for a hidden (quiet-apply) launched window
        self._quiet_window_id: int | None = None
        # Default True: no import has failed (yet). Only a launched-profile
        # run whose import actually found a file and failed to restore it
        # sets this False, in which case __exit__ must skip the export
        # entirely rather than overwrite a good file with an empty one
        # (verifier FIX-FIRST 1, 2026-08-25).
        self._cookie_import_ok = True

    def __enter__(self) -> "Session":
        self._playwright = sync_playwright().start()
        try:
            effective_headed = _effective_headed(self.mode, self.config)
            headless_flag = not effective_headed
            if self.config.cdp_url:
                self._browser = self._playwright.chromium.connect_over_cdp(self.config.cdp_url)
                self.context = (
                    self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                )
                # Always a brand-new tab: an attached context may already
                # hold the Director's own actively-used tabs, which Headless
                # must never read from, type into, or screenshot. Never
                # hidden/minimized either - that would be the Director's own
                # whole browser window, not something Headless launched.
                self.page = self.context.new_page()
            else:
                Path(self.config.profile_dir).mkdir(parents=True, exist_ok=True)
                self.context = self._playwright.chromium.launch_persistent_context(
                    str(self.config.profile_dir),
                    channel="chrome",
                    headless=headless_flag,
                    chromium_sandbox=True,
                )
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                self._cookie_import_ok = _import_session_cookies(self.context, self.config.profile_dir)
                if _should_hide_window(self.mode, self.config):
                    self._hide_window()
        except PlaywrightError as exc:
            self._playwright.stop()
            self._playwright = None
            message = str(exc)
            if any(hint in message for hint in _PROFILE_LOCK_HINTS):
                raise GateRefused(
                    f"profile in use: {self.config.profile_dir} is locked by another Headless run"
                ) from exc
            raise
        except Exception:
            # Any other failure (e.g. PermissionError creating profile_dir)
            # must still stop the Playwright driver before propagating.
            self._playwright.stop()
            self._playwright = None
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.config.cdp_url:
                # CDP attach: close only the page Headless opened, then
                # disconnect. This never touches the Director's other tabs
                # or terminates their actual Chrome process.
                if self.page is not None:
                    try:
                        self.page.close()
                    except PlaywrightError:
                        pass
                if self._browser is not None:
                    self._browser.close()
            else:
                if self.context is not None:
                    # A failed import (a state file existed but could not be
                    # restored) must never let this unconditional export
                    # overwrite that still-good file with an empty one - skip
                    # the export in that case only; the context still closes
                    # normally either way (verifier FIX-FIRST 1, 2026-08-25).
                    if self._cookie_import_ok:
                        _export_session_cookies(self.context, self.config.profile_dir)
                    self.context.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()
                self._playwright = None

    def _hide_window(self) -> None:
        """Best-effort: hide the just-launched apply window until handoff().
        Never fatal - if every mechanism below is a no-op on this machine
        (see the module-level comment above _OFFSCREEN_LEFT), the run
        continues with a normal, visible window rather than failing."""
        try:
            cdp = self.context.new_cdp_session(self.page)
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]
            # Remember the handle immediately so a partial hide is always restorable.
            self._quiet_cdp = cdp
            self._quiet_window_id = window_id
            cdp.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"windowState": "minimized"}},
            )
            cdp.send(
                "Browser.setWindowBounds",
                {"windowId": window_id, "bounds": {"left": _OFFSCREEN_LEFT, "top": _OFFSCREEN_TOP}},
            )
        except Exception:
            pass

    def _restore_window(self) -> None:
        """Undo _hide_window at the handoff: normal state, on-screen position, focus."""
        if self._quiet_cdp is None or self._quiet_window_id is None:
            return
        try:
            self._quiet_cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": self._quiet_window_id,
                    "bounds": {"left": _RESTORE_LEFT, "top": _RESTORE_TOP, "windowState": "normal"},
                },
            )
            self.page.bring_to_front()
        except Exception:
            pass

    def goto(self, url: str) -> None:
        try:
            self.page.goto(url)
        except PlaywrightError:
            self.page.goto(url)  # one retry on a transient navigation error

    def probe(self, selectors: list[str]) -> list[tuple[str, bool]]:
        return [(selector, self.page.locator(selector).count() > 0) for selector in selectors]

    def fill(self, plan: FieldPlan, vault: VaultBackend, registry: ProfileRegistry) -> None:
        if self.mode is not Mode.APPLY:
            raise GateRefused("fill is only permitted in apply mode")
        if plan.kind not in ("fill", "select", "check"):
            # A programming error in the errand script, not a browser/site
            # failure - raised before resolving anything, never wrapped.
            raise ValueError(f"unknown FieldPlan.kind: {plan.kind!r}")

        value = resolve_source(plan.source, vault, registry)
        locator = self.page.locator(plan.selector)
        try:
            if plan.kind == "fill":
                locator.fill(value)
            elif plan.kind == "select":
                locator.select_option(value)
            else:  # "check"
                if value.strip().lower() in ("1", "true", "yes", "on"):
                    locator.check()
                else:
                    locator.uncheck()
        except Exception as exc:
            # Playwright's own exception (e.g. a Locator.fill timeout) embeds
            # its call log, which can contain the raw value just typed. Never
            # let that object or its message propagate; re-raise a FillFailed
            # built only from redacted, structural information.
            raise FillFailed(plan, value, exc) from None

    def screenshot(self) -> bytes | None:
        try:
            style_handle = self.page.add_style_tag(content=_SCREENSHOT_MASK_CSS)
        except PlaywrightError:
            # The page's own CSP (e.g. style-src 'self') can refuse the
            # mask's inline <style> injection. Never fall back to capturing
            # unmasked: skip the screenshot entirely, same as
            # --no-screenshot (Errand.run/write_artifacts already treat a
            # None screenshot that way).
            print("note: screenshot skipped, the page's CSP blocked the mask")
            return None
        try:
            return self.page.screenshot()
        finally:
            style_handle.evaluate("e => e.remove()")

    def handoff(self, handoff_text: str) -> bool:
        self._restore_window()
        print(f"Your turn: {handoff_text}")
        self._confirm()
        try:
            return not self.page.is_closed()
        except PlaywrightError:
            return False
