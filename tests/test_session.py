"""Unit test for headless/session.py's screenshot masking path
(Session.screenshot), using a stub page instead of a real browser, so it runs
in the fast, browser-free commit-gate suite (BLOCK 2a).
"""

from __future__ import annotations

import json
import os
import stat

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

from dataclasses import replace

import headless.session as session_module
from headless.config import Config
from headless.fields import parse_source, FieldPlan
from headless.gates import GateRefused, Mode
from headless.session import (
    SESSION_COOKIE_FILENAME,
    FillFailed,
    Session,
    _SCREENSHOT_MASK_CSS,
    _effective_headed,
    _export_session_cookies,
    _import_session_cookies,
    _session_cookie_path,
    _should_hide_window,
)


class _StubStyleHandle:
    def __init__(self) -> None:
        self.removed = False

    def evaluate(self, script: str) -> None:
        assert script == "e => e.remove()"
        self.removed = True


class _StubPage:
    def __init__(self) -> None:
        self.add_style_tag_calls: list[str] = []
        self.style_handle = _StubStyleHandle()
        self.screenshot_called = False

    def add_style_tag(self, content: str):
        self.add_style_tag_calls.append(content)
        return self.style_handle

    def screenshot(self) -> bytes:
        self.screenshot_called = True
        return b"stub-png-bytes"


def _bare_session() -> Session:
    # Bypass __init__ (no real Playwright launch needed for a pure unit test
    # of the screenshot masking path).
    session = Session.__new__(Session)
    session.config = Config(
        profile_dir=Path("/tmp/headless-test-unused"),
        headed=True,
        cdp_url=None,
        secrets_backend="keychain",
        keychain_account="unused",
        gcp_project=None,
        preview_dir=Path("/tmp/headless-test-unused-previews"),
    )
    session.mode = Mode.PREVIEW
    session.page = _StubPage()
    session.context = None
    session._quiet_cdp = None
    session._quiet_window_id = None
    return session


def test_screenshot_applies_then_removes_the_mask_style():
    session = _bare_session()

    result = session.screenshot()

    assert result == b"stub-png-bytes"
    assert session.page.add_style_tag_calls == [_SCREENSHOT_MASK_CSS]
    assert session.page.screenshot_called is True
    assert session.page.style_handle.removed is True


def test_mask_css_covers_inputs_textareas_and_selects():
    assert "input" in _SCREENSHOT_MASK_CSS
    assert "textarea" in _SCREENSHOT_MASK_CSS
    assert "select" in _SCREENSHOT_MASK_CSS
    assert "-webkit-text-security" in _SCREENSHOT_MASK_CSS


# --- FIX-FIRST 7: fill() refused outside apply; headless-apply refusal -----


def test_fill_refused_in_preview_mode():
    session = _bare_session()
    session.mode = Mode.PREVIEW
    plan = FieldPlan(name="X", selector="#x", source=parse_source("literal:y"))
    with pytest.raises(GateRefused, match="apply mode"):
        session.fill(plan, vault=None, registry=None)


def test_fill_refused_in_check_mode():
    session = _bare_session()
    session.mode = Mode.CHECK
    plan = FieldPlan(name="X", selector="#x", source=parse_source("literal:y"))
    with pytest.raises(GateRefused, match="apply mode"):
        session.fill(plan, vault=None, registry=None)


def _headless_config() -> Config:
    return Config(
        profile_dir=Path("/tmp/headless-test-unused"),
        headed=False,
        cdp_url=None,
        secrets_backend="keychain",
        keychain_account="unused",
        gcp_project=None,
        preview_dir=Path("/tmp/headless-test-unused-previews"),
    )


def test_apply_constructor_refuses_headless_without_bypass():
    with pytest.raises(GateRefused, match="visible browser"):
        Session(_headless_config(), Mode.APPLY)


def test_apply_constructor_allows_headless_with_explicit_test_bypass():
    # Construction only (no __enter__/real launch); the bypass must be an
    # explicit constructor argument, never reachable from the CLI.
    session = Session(_headless_config(), Mode.APPLY, allow_headless_apply_for_tests=True)
    assert session.mode is Mode.APPLY


# --- N1: a CSP-blocked mask must never fall back to an unmasked capture ----


class _CspBlockedStylePage:
    """A stub page whose add_style_tag always raises, simulating a page CSP
    (style-src 'self') refusing the mask's inline <style> injection."""

    def __init__(self) -> None:
        self.screenshot_called = False

    def add_style_tag(self, content: str):
        raise PlaywrightError(
            "Page.add_style_tag: Applying inline style violates the following "
            "Content Security Policy directive 'style-src 'self''."
        )

    def screenshot(self) -> bytes:
        # Must never be reached: a CSP failure skips the screenshot entirely
        # rather than falling back to an unmasked capture.
        self.screenshot_called = True
        return b"UNMASKED-SHOULD-NEVER-BE-RETURNED"


def test_screenshot_returns_none_and_prints_note_when_csp_blocks_the_mask(capsys):
    session = _bare_session()
    session.page = _CspBlockedStylePage()

    result = session.screenshot()

    assert result is None
    assert session.page.screenshot_called is False
    out = capsys.readouterr().out
    assert out.strip() == "note: screenshot skipped, the page's CSP blocked the mask"


# --- N5: Session.fill must never leak a raw value through FillFailed -------


class _RawValueLeakingLocator:
    def fill(self, value: str) -> None:
        raise RuntimeError(f'Locator.fill: Timeout exceeded.\nCall log:\n  - fill("{value}")')


class _PageWithRawValueLeakingLocator:
    def locator(self, selector: str):
        return _RawValueLeakingLocator()


def test_fill_wraps_locator_exception_without_leaking_the_raw_value():
    raw_value = "TOTALLY-SECRET-RAW-VALUE-12345"
    session = _bare_session()
    session.mode = Mode.APPLY
    session.page = _PageWithRawValueLeakingLocator()

    plan = FieldPlan(name="Notes", selector="#notes", source=parse_source(f"literal:{raw_value}"))

    with pytest.raises(FillFailed) as exc_info:
        session.fill(plan, vault=None, registry=None)

    assert raw_value not in str(exc_info.value)
    assert raw_value not in repr(exc_info.value)


# --- Quiet by default (Director decision 2026-08-24): resolution table -----


def _config(**overrides) -> Config:
    base = Config(
        profile_dir=Path("/tmp/headless-test-unused"),
        headed=True,
        cdp_url=None,
        secrets_backend="keychain",
        keychain_account="unused",
        gcp_project=None,
        preview_dir=Path("/tmp/headless-test-unused-previews"),
    )
    return replace(base, **overrides)


def test_preview_and_check_are_invisible_by_default():
    config = _config(headed=True, show=False)
    assert _effective_headed(Mode.PREVIEW, config) is False
    assert _effective_headed(Mode.CHECK, config) is False


def test_preview_and_check_ignore_headed_env_and_use_show():
    # "regardless of HEADLESS_HEADED": headed=True alone must not make
    # preview/check visible.
    config = _config(headed=True, show=False)
    assert _effective_headed(Mode.PREVIEW, config) is False
    # even headed=False changes nothing for preview/check - show is what matters
    config2 = _config(headed=False, show=False)
    assert _effective_headed(Mode.PREVIEW, config2) is False


def test_show_makes_preview_and_check_visible():
    config = _config(headed=True, show=True)
    assert _effective_headed(Mode.PREVIEW, config) is True
    assert _effective_headed(Mode.CHECK, config) is True


def test_apply_uses_headed_regardless_of_show():
    config = _config(headed=True, show=False)
    assert _effective_headed(Mode.APPLY, config) is True
    # the test-bypass shape (headed=False + allow_headless_apply_for_tests):
    # apply must still resolve to invisible so the browser suite stays fast.
    config2 = _config(headed=False, show=True)
    assert _effective_headed(Mode.APPLY, config2) is False


def test_headless_flag_refused_with_apply_via_argparse():
    # --headless and --apply combined is refused at the CLI layer (argparse
    # mutually-exclusive group on --apply/--check already existed; --headless
    # is refused with --apply through the existing headed=False gate in
    # resolve_mode, unchanged by "quiet by default").
    from headless.gates import GateRefused, add_mode_arguments, resolve_mode
    import argparse

    parser = argparse.ArgumentParser()
    add_mode_arguments(parser)
    args = parser.parse_args(["--apply", "--headless"])
    with pytest.raises(GateRefused, match="visible browser"):
        resolve_mode(args, isatty=True, headed=False)


def test_headless_and_show_are_mutually_exclusive_flags():
    import argparse

    from headless.gates import add_mode_arguments

    parser = argparse.ArgumentParser()
    add_mode_arguments(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--headless", "--show"])


# --- Quiet by default: the minimize CDP calls, via a stub context/page -----


class _StubCdpSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def send(self, method: str, params: dict | None = None):
        self.calls.append((method, params or {}))
        if method == "Browser.getWindowForTarget":
            return {"windowId": 42}
        return {}


class _StubContextForHiding:
    def __init__(self) -> None:
        self.cdp_session = _StubCdpSession()

    def new_cdp_session(self, page):
        return self.cdp_session


class _StubPageWithBringToFront:
    def __init__(self) -> None:
        self.bring_to_front_called = False

    def bring_to_front(self) -> None:
        self.bring_to_front_called = True


def test_hide_window_issues_minimize_then_offscreen_cdp_calls():
    session = _bare_session()
    session.context = _StubContextForHiding()

    session._hide_window()

    methods = [call[0] for call in session.context.cdp_session.calls]
    assert methods == [
        "Browser.getWindowForTarget",
        "Browser.setWindowBounds",
        "Browser.setWindowBounds",
    ]
    minimize_call, offscreen_call = session.context.cdp_session.calls[1], session.context.cdp_session.calls[2]
    assert minimize_call[1]["bounds"]["windowState"] == "minimized"
    assert offscreen_call[1]["bounds"]["left"] > 0
    assert offscreen_call[1]["bounds"]["top"] > 0


def test_restore_window_sets_normal_state_and_brings_to_front():
    session = _bare_session()
    session.context = _StubContextForHiding()
    session.page = _StubPageWithBringToFront()
    session._hide_window()

    session._restore_window()

    last_method, last_params = session.context.cdp_session.calls[-1]
    assert last_method == "Browser.setWindowBounds"
    assert last_params["bounds"]["windowState"] == "normal"
    assert session.page.bring_to_front_called is True


def test_restore_window_is_a_no_op_when_never_hidden():
    # e.g. preview/check, or apply with --show: handoff() calls
    # _restore_window() unconditionally, and it must do nothing when
    # _hide_window() was never called.
    session = _bare_session()
    session.page = _StubPageWithBringToFront()

    session._restore_window()  # must not raise

    assert session.page.bring_to_front_called is False


def test_should_hide_window_true_for_apply_without_show():
    config = _config(headed=True, show=False)
    assert _should_hide_window(Mode.APPLY, config) is True


def test_should_hide_window_false_for_apply_with_show():
    config = _config(headed=True, show=True)
    assert _should_hide_window(Mode.APPLY, config) is False


def test_should_hide_window_false_for_preview_and_check_regardless_of_show():
    for show in (True, False):
        config = _config(headed=True, show=show)
        assert _should_hide_window(Mode.PREVIEW, config) is False
        assert _should_hide_window(Mode.CHECK, config) is False


# --- v0.0.3: session cookie persistence (spec 003-login-persistence) -------
#
# Every test below uses an obviously synthetic cookie value (never a value
# shaped like a real credential), per quickstart Scenario 7 and PATTERNS.md's
# masking convention.

_SYNTHETIC_COOKIE = {
    "name": "sess",
    "value": "SYNTHETIC-SESS-VALUE-1",
    "domain": "example.com",
    "path": "/",
    "expires": -1,
    "httpOnly": True,
    "secure": True,
    "sameSite": "Lax",
}

_SYNTHETIC_EXPIRING_COOKIE = {
    "name": "tracking",
    "value": "does-not-matter",
    "domain": "example.com",
    "path": "/",
    "expires": 1.0,  # a real (non-session) expiry: not -1, so not a session cookie
    "httpOnly": False,
    "secure": True,
    "sameSite": "Lax",
}


class _FakeCookieContext:
    """Stands in for a Playwright BrowserContext for the import/export unit
    tests below: no real browser, just enough surface for
    _import_session_cookies/_export_session_cookies to call."""

    def __init__(self, cookies_to_return=None, add_cookies_exception=None):
        self._cookies = cookies_to_return if cookies_to_return is not None else []
        self.add_cookies_calls: list[list[dict]] = []
        self._add_cookies_exception = add_cookies_exception

    def cookies(self):
        return self._cookies

    def add_cookies(self, entries):
        self.add_cookies_calls.append(entries)
        if self._add_cookies_exception is not None:
            raise self._add_cookies_exception


# --- T003: import ------------------------------------------------------


def test_import_missing_state_file_is_silent_and_imports_nothing(tmp_path, capsys):
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == []
    assert capsys.readouterr().out == ""


def test_import_valid_state_file_hands_entries_to_add_cookies(tmp_path, capsys):
    _session_cookie_path(tmp_path).write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == [[_SYNTHETIC_COOKIE]]
    assert capsys.readouterr().out == ""


def test_import_malformed_json_prints_one_note_and_imports_nothing(tmp_path, capsys):
    _session_cookie_path(tmp_path).write_text("{not valid json", encoding="utf-8")
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == []
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("note: session cookies not restored (")


def test_import_valid_json_but_not_a_list_prints_one_note(tmp_path, capsys):
    _session_cookie_path(tmp_path).write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == []
    out = capsys.readouterr().out.strip()
    assert out.startswith("note: session cookies not restored (")


def test_import_empty_file_is_a_parse_failure_not_a_special_case(tmp_path, capsys):
    _session_cookie_path(tmp_path).write_text("", encoding="utf-8")
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == []
    out = capsys.readouterr().out.strip()
    assert out.startswith("note: session cookies not restored (")


def test_import_succeeds_even_when_file_mode_is_looser_than_0600(tmp_path, capsys):
    path = _session_cookie_path(tmp_path)
    path.write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
    os.chmod(path, 0o644)  # looser than 0600; only export enforces the mode (research.md D6)
    context = _FakeCookieContext()

    _import_session_cookies(context, tmp_path)

    assert context.add_cookies_calls == [[_SYNTHETIC_COOKIE]]
    assert capsys.readouterr().out == ""


# --- T004: export --------------------------------------------------------


def test_export_writes_only_session_cookies_not_expiring_ones(tmp_path):
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE, _SYNTHETIC_EXPIRING_COOKIE])

    _export_session_cookies(context, tmp_path)

    written = json.loads(_session_cookie_path(tmp_path).read_text(encoding="utf-8"))
    assert written == [_SYNTHETIC_COOKIE]


def test_export_replaces_atomically_via_a_temp_file_in_the_same_directory(tmp_path, monkeypatch):
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])
    replace_calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy_replace(src, dst):
        replace_calls.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(session_module.os, "replace", spy_replace)

    _export_session_cookies(context, tmp_path)

    assert len(replace_calls) == 1
    src, dst = replace_calls[0]
    assert src == str(tmp_path / f"{SESSION_COOKIE_FILENAME}.tmp")
    assert dst == str(_session_cookie_path(tmp_path))
    assert _session_cookie_path(tmp_path).exists()


def test_export_leaves_the_file_at_mode_0600_on_first_write(tmp_path):
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])

    _export_session_cookies(context, tmp_path)

    mode = stat.S_IMODE(_session_cookie_path(tmp_path).stat().st_mode)
    assert mode == 0o600


def test_export_corrects_a_looser_mode_on_replace(tmp_path):
    # T021: a state file that existed before the run at a looser-than-0600
    # mode is corrected to exactly 0600 by the next export (the "replace"
    # case of FR-005's "whether created or replaced" clause).
    path = _session_cookie_path(tmp_path)
    path.write_text("[]", encoding="utf-8")
    os.chmod(path, 0o644)
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])

    _export_session_cookies(context, tmp_path)

    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_export_write_failure_prints_one_note_and_never_raises(tmp_path, monkeypatch, capsys):
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])

    def raising_open(*args, **kwargs):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(session_module.os, "open", raising_open)

    _export_session_cookies(context, tmp_path)  # must not raise

    out = capsys.readouterr().out.strip()
    assert out.startswith("note: session cookies not saved (")
    assert not _session_cookie_path(tmp_path).exists()


# --- T005: add_cookies failure + no-leak coverage ---------------------------


def test_import_add_cookies_failure_prints_one_note_zero_imported(tmp_path, capsys):
    _session_cookie_path(tmp_path).write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
    context = _FakeCookieContext(add_cookies_exception=RuntimeError("rejected"))

    _import_session_cookies(context, tmp_path)

    assert len(context.add_cookies_calls) == 1  # called once, treated as a total failure
    out = capsys.readouterr().out.strip()
    assert out.startswith("note: session cookies not restored (")


@pytest.mark.parametrize(
    "scenario",
    ["missing", "valid", "malformed", "empty", "add_cookies_raises", "export_success", "export_failure"],
)
def test_cookie_value_never_appears_in_captured_output(tmp_path, capsys, scenario):
    """T005/T020: every import/export scenario, run against one distinctive
    synthetic cookie value, must never let that value reach captured
    stdout/stderr (SC-005, NFR-001)."""
    if scenario == "missing":
        _import_session_cookies(_FakeCookieContext(), tmp_path)
    elif scenario == "valid":
        _session_cookie_path(tmp_path).write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
        _import_session_cookies(_FakeCookieContext(), tmp_path)
    elif scenario == "malformed":
        _session_cookie_path(tmp_path).write_text(
            '{"value": "' + _SYNTHETIC_COOKIE["value"] + '"', encoding="utf-8"
        )
        _import_session_cookies(_FakeCookieContext(), tmp_path)
    elif scenario == "empty":
        _session_cookie_path(tmp_path).write_text("", encoding="utf-8")
        _import_session_cookies(_FakeCookieContext(), tmp_path)
    elif scenario == "add_cookies_raises":
        _session_cookie_path(tmp_path).write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
        # The exception message itself carries the value, proving the note
        # only ever uses the exception's class name, never its message.
        _import_session_cookies(
            _FakeCookieContext(add_cookies_exception=RuntimeError(_SYNTHETIC_COOKIE["value"])), tmp_path
        )
    elif scenario == "export_success":
        _export_session_cookies(_FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE]), tmp_path)
    else:  # export_failure - same "message carries the value" proof, export side

        class _ExplodingCookieContext(_FakeCookieContext):
            def cookies(self):
                raise RuntimeError(_SYNTHETIC_COOKIE["value"])

        _export_session_cookies(_ExplodingCookieContext(), tmp_path)

    captured = capsys.readouterr()
    assert _SYNTHETIC_COOKIE["value"] not in captured.out
    assert _SYNTHETIC_COOKIE["value"] not in captured.err


# --- T009: two successive launches share state via the file ----------------


def test_export_then_import_session_cookie_across_two_contexts_shares_state(tmp_path):
    """Simulates two successive launches against the same profile directory
    (the second only after the first's simulated __exit__ has written the
    state file): a session cookie the first context's cookies() reports at
    close must be present in the arguments the second context's
    add_cookies() receives at the next open - proving the wiring end to
    end through the shared state file, not just the two functions in
    isolation."""
    profile_dir = tmp_path / "chrome-profile"
    profile_dir.mkdir()

    first_context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])
    _export_session_cookies(first_context, profile_dir)  # simulates __exit__

    second_context = _FakeCookieContext()
    _import_session_cookies(second_context, profile_dir)  # simulates __enter__

    assert second_context.add_cookies_calls == [[_SYNTHETIC_COOKIE]]


# --- Fakes for a full Session.__enter__/__exit__ round trip, no real -------
# --- browser: monkeypatch the sync_playwright() seam session.py calls. -----


class _FakePageForLaunch:
    pass


class _FakeLaunchedContext(_FakeCookieContext):
    """_FakeCookieContext plus the extra surface Session.__enter__/__exit__
    needs on the launched-profile path (pages/new_page/close)."""

    def __init__(self, cookies_to_return=None, add_cookies_exception=None):
        super().__init__(cookies_to_return=cookies_to_return, add_cookies_exception=add_cookies_exception)
        self.pages: list = []
        self.closed = False

    def new_page(self):
        page = _FakePageForLaunch()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class _FakeChromiumForLaunch:
    def __init__(self, context):
        self._context = context
        self.launch_calls: list[tuple[tuple, dict]] = []

    def launch_persistent_context(self, *args, **kwargs):
        self.launch_calls.append((args, kwargs))
        return self._context


class _FakePlaywrightObj:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeSyncPlaywrightHandle:
    """Stands in for what `sync_playwright()` returns: `.start()` (what
    Session.__enter__ calls) and the `with ... as p:` protocol (what
    check_env.py uses) both resolve to the same fake Playwright object."""

    def __init__(self, playwright_obj):
        self._playwright_obj = playwright_obj

    def start(self):
        return self._playwright_obj

    def __enter__(self):
        return self._playwright_obj

    def __exit__(self, *exc_info):
        return False


# --- T014: chromium_sandbox launch-kwargs (US2) -----------------------------


def test_launched_profile_session_passes_chromium_sandbox_true(tmp_path, monkeypatch):
    context = _FakeLaunchedContext()
    chromium = _FakeChromiumForLaunch(context)
    monkeypatch.setattr(
        session_module, "sync_playwright", lambda: _FakeSyncPlaywrightHandle(_FakePlaywrightObj(chromium))
    )

    config = _config(profile_dir=tmp_path / "chrome-profile", headed=False, show=False)
    session = Session(config, Mode.PREVIEW)
    session.__enter__()
    try:
        assert len(chromium.launch_calls) == 1
        _args, kwargs = chromium.launch_calls[0]
        assert kwargs["chromium_sandbox"] is True
    finally:
        session.__exit__(None, None, None)


# --- T019: CDP-attach path never touches the state file (FR-012, SC-006) ---


class _FakeCdpPage:
    def close(self) -> None:
        pass


class _FakeCdpContext:
    def __init__(self) -> None:
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        return _FakeCdpPage()


class _FakeCdpBrowser:
    def __init__(self, context) -> None:
        self.contexts = [context]
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeChromiumForCdp:
    def __init__(self, browser) -> None:
        self._browser = browser

    def connect_over_cdp(self, url):
        return self._browser


def test_cdp_cookie_state_file_never_touched_on_the_cdp_attach_path(tmp_path, monkeypatch):
    context = _FakeCdpContext()
    browser = _FakeCdpBrowser(context)
    playwright_obj = _FakePlaywrightObj(_FakeChromiumForCdp(browser))
    monkeypatch.setattr(
        session_module, "sync_playwright", lambda: _FakeSyncPlaywrightHandle(playwright_obj)
    )

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("must not be called on the CDP-attach path")

    monkeypatch.setattr(session_module, "_import_session_cookies", _must_not_be_called)
    monkeypatch.setattr(session_module, "_export_session_cookies", _must_not_be_called)

    profile_dir = tmp_path / "cdp-profile-unused"
    config = _config(profile_dir=profile_dir, cdp_url="http://127.0.0.1:9222", headed=True, show=False)

    with Session(config, Mode.PREVIEW):
        pass

    assert not profile_dir.exists()
    assert context.new_page_calls == 1


# --- T020: a full launched-profile round trip never leaks the value --------


def test_full_launched_profile_lifecycle_never_leaks_the_cookie_value(tmp_path, monkeypatch, capsys):
    """A single cross-cutting proof, on top of the per-scenario assertions
    above: a real __enter__/__exit__ round trip (fake launch, export, then a
    fake relaunch that imports what was just exported) never lets the
    synthetic cookie's value reach stdout/stderr, and the second launch's
    context really does receive it via add_cookies (SC-005, NFR-001)."""
    profile_dir = tmp_path / "chrome-profile"
    config = _config(profile_dir=profile_dir, headed=False, show=False)

    context1 = _FakeLaunchedContext(cookies_to_return=[_SYNTHETIC_COOKIE])
    monkeypatch.setattr(
        session_module,
        "sync_playwright",
        lambda: _FakeSyncPlaywrightHandle(_FakePlaywrightObj(_FakeChromiumForLaunch(context1))),
    )
    with Session(config, Mode.PREVIEW):
        pass  # __exit__ exports context1's session cookie to profile_dir

    context2 = _FakeLaunchedContext()
    monkeypatch.setattr(
        session_module,
        "sync_playwright",
        lambda: _FakeSyncPlaywrightHandle(_FakePlaywrightObj(_FakeChromiumForLaunch(context2))),
    )
    with Session(config, Mode.PREVIEW):
        pass  # __enter__ imports the state file context1 just wrote

    assert context2.add_cookies_calls == [[_SYNTHETIC_COOKIE]]
    captured = capsys.readouterr()
    assert _SYNTHETIC_COOKIE["value"] not in captured.out
    assert _SYNTHETIC_COOKIE["value"] not in captured.err


# --- Opus verifier, 2026-08-25: FIX-FIRST 1 ---------------------------------
# A failed import must never let __exit__'s unconditional export overwrite a
# good, previously exported file with an empty one.


def test_import_returns_true_when_no_file_or_import_succeeds(tmp_path):
    assert _import_session_cookies(_FakeCookieContext(), tmp_path) is True

    _session_cookie_path(tmp_path).write_text(json.dumps([_SYNTHETIC_COOKIE]), encoding="utf-8")
    assert _import_session_cookies(_FakeCookieContext(), tmp_path) is True


def test_import_returns_false_only_when_a_file_existed_and_failed(tmp_path):
    _session_cookie_path(tmp_path).write_text("{not valid json", encoding="utf-8")
    assert _import_session_cookies(_FakeCookieContext(), tmp_path) is False


def test_full_session_exit_skips_export_when_import_failed_via_add_cookies(tmp_path, monkeypatch):
    """FIX-FIRST 1: going through the real Session.__enter__/__exit__
    lifecycle (not just the raw functions) - a state file that exists but
    whose import fails because context.add_cookies() rejects the batch
    (e.g. Playwright's driver asserting "Cookie should have a name") must
    still exist, byte-for-byte unchanged, after __exit__ runs."""
    profile_dir = tmp_path / "chrome-profile"
    profile_dir.mkdir()
    original_content = json.dumps([_SYNTHETIC_COOKIE])
    _session_cookie_path(profile_dir).write_text(original_content, encoding="utf-8")

    context = _FakeLaunchedContext(add_cookies_exception=RuntimeError("Cookie should have a name"))
    monkeypatch.setattr(
        session_module,
        "sync_playwright",
        lambda: _FakeSyncPlaywrightHandle(_FakePlaywrightObj(_FakeChromiumForLaunch(context))),
    )

    config = _config(profile_dir=profile_dir, headed=False, show=False)
    with Session(config, Mode.PREVIEW):
        pass  # __enter__'s import fails; __exit__ must skip the export

    assert _session_cookie_path(profile_dir).read_text(encoding="utf-8") == original_content


def test_full_session_exit_skips_export_when_import_failed_malformed_file(tmp_path, monkeypatch):
    """FIX-FIRST 1, malformed-file variant: same guarantee when the state
    file exists but is not valid JSON, rather than add_cookies() rejecting
    it."""
    profile_dir = tmp_path / "chrome-profile"
    profile_dir.mkdir()
    original_content = "{not valid json"
    _session_cookie_path(profile_dir).write_text(original_content, encoding="utf-8")

    context = _FakeLaunchedContext()
    monkeypatch.setattr(
        session_module,
        "sync_playwright",
        lambda: _FakeSyncPlaywrightHandle(_FakePlaywrightObj(_FakeChromiumForLaunch(context))),
    )

    config = _config(profile_dir=profile_dir, headed=False, show=False)
    with Session(config, Mode.PREVIEW):
        pass  # __enter__'s import fails; __exit__ must skip the export

    assert _session_cookie_path(profile_dir).read_text(encoding="utf-8") == original_content
    # The export step never even runs, so context.cookies() is never called.
    assert context.add_cookies_calls == []


# --- Opus verifier, 2026-08-25: FIX-FIRST 2 ---------------------------------
# A failure between the temp write and the atomic replace must never leave a
# plaintext-cookie .tmp file behind.


def test_export_failure_after_tmp_write_removes_the_tmp_file(tmp_path, monkeypatch):
    context = _FakeCookieContext(cookies_to_return=[_SYNTHETIC_COOKIE])

    def raising_replace(src, dst):
        raise OSError("replace failed (simulated)")

    monkeypatch.setattr(session_module.os, "replace", raising_replace)

    _export_session_cookies(context, tmp_path)  # must not raise

    tmp_file = tmp_path / f"{SESSION_COOKIE_FILENAME}.tmp"
    assert not tmp_file.exists()
    assert list(tmp_path.iterdir()) == []  # nothing left behind at all
