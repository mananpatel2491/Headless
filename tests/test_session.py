"""Unit test for headless/session.py's screenshot masking path
(Session.screenshot), using a stub page instead of a real browser, so it runs
in the fast, browser-free commit-gate suite (BLOCK 2a).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

from dataclasses import replace

from headless.config import Config
from headless.fields import parse_source, FieldPlan
from headless.gates import GateRefused, Mode
from headless.session import (
    FillFailed,
    Session,
    _SCREENSHOT_MASK_CSS,
    _effective_headed,
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
