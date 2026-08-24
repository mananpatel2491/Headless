"""Unit tests for headless/errand.py: the run() state machine with a stubbed
Session (no browser, no real vault) so preview/check/apply and the refusal
paths are proven without touching a window or the Keychain.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from headless.errand import Errand
from headless.fields import FieldPlan, parse_source
from headless.gates import Mode

RAW_EMAIL_SECRET = "director@example.com"
RAW_REGISTRY_VALUE = "Director Name"


class FakeSession:
    """Stand-in for headless.session.Session: records every call, never opens
    a browser, and its handoff() never blocks on real input()."""

    instances: list["FakeSession"] = []

    def __init__(self, config, mode, *, confirm=input, allow_headless_apply_for_tests=False):
        self.config = config
        self.mode = mode
        self.goto_calls: list[str] = []
        self.fill_calls: list[FieldPlan] = []
        self.probe_calls: list[list[str]] = []
        self.handoff_calls: list[str] = []
        self.page = SimpleNamespace(
            url="https://example.com/",
            title=lambda: "Example Domain",
            is_closed=lambda: False,
        )
        FakeSession.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def goto(self, url):
        self.goto_calls.append(url)

    def probe(self, selectors):
        self.probe_calls.append(list(selectors))
        return [(selector, selector != "#does-not-exist") for selector in selectors]

    def fill(self, plan, vault, registry):
        self.fill_calls.append(plan)

    def screenshot(self):
        return b"fake-png-bytes"

    def handoff(self, text):
        self.handoff_calls.append(text)
        return True


def _default_plan(registry):
    return [
        FieldPlan(name="Full name", selector="#full_name", source=parse_source("registry:identity.full_name")),
        FieldPlan(name="Email", selector="#email", source=parse_source("secret:test-email")),
        FieldPlan(name="Form type", selector="#form_type", source=parse_source("literal:ITR-2"), kind="select"),
    ]


class DummyErrand(Errand):
    """A stand-in errand used only by these tests."""

    name = "dummy"
    HANDOFF = "n/a (test)"
    dependencies = ["#pan", "#does-not-exist"]

    def __init__(self, plan_fn=None):
        self._plan_fn = plan_fn or _default_plan

    def add_arguments(self, parser):
        parser.add_argument("--target-url", default="https://example.com")

    def url(self, args):
        return args.target_url

    def plan(self, registry):
        return self._plan_fn(registry)


@pytest.fixture(autouse=True)
def reset_fake_session():
    FakeSession.instances.clear()
    yield
    FakeSession.instances.clear()


@pytest.fixture
def wired_vault(fake_vault):
    fake_vault.put_secret("profile", json.dumps({"identity": {"full_name": RAW_REGISTRY_VALUE}}))
    fake_vault.put_secret("test-email", RAW_EMAIL_SECRET)
    return fake_vault


@pytest.fixture
def patched_errand_deps(monkeypatch, wired_vault):
    monkeypatch.setattr("headless.errand.Session", FakeSession)
    monkeypatch.setattr("headless.errand.open_vault", lambda config: wired_vault)
    return wired_vault


def test_preview_run_produces_masked_record_and_no_fill(patched_errand_deps, tmp_path, capsys):
    errand = DummyErrand()
    exit_code = errand.run(["--preview-dir", str(tmp_path)])

    assert exit_code == 0
    session = FakeSession.instances[-1]
    assert session.mode is Mode.PREVIEW
    assert session.fill_calls == []
    assert session.goto_calls == ["https://example.com"]

    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0] == "Title: Example Domain"
    assert lines[-1].startswith("PREVIEW ")
    json_path = lines[-1].removeprefix("PREVIEW ").strip()
    payload = json.loads(open(json_path, encoding="utf-8").read())
    assert payload["mode"] == "preview"
    names = {f["name"] for f in payload["fields"]}
    assert names == {"Full name", "Email", "Form type"}
    assert RAW_EMAIL_SECRET not in json.dumps(payload)
    assert RAW_REGISTRY_VALUE not in json.dumps(payload)
    # NIT 14: the raw values must never reach stdout either, not just the JSON.
    assert RAW_EMAIL_SECRET not in out
    assert RAW_REGISTRY_VALUE not in out


def test_check_run_calls_probe_with_dependencies_and_no_fill(patched_errand_deps, tmp_path, capsys):
    errand = DummyErrand()
    exit_code = errand.run(["--check", "--preview-dir", str(tmp_path)])

    assert exit_code == 0
    session = FakeSession.instances[-1]
    assert session.mode is Mode.CHECK
    assert session.probe_calls == [DummyErrand.dependencies]
    assert session.fill_calls == []
    out = capsys.readouterr().out
    assert "CHECK 1 found, 1 missing" in out


def test_apply_run_fills_each_plan_then_handoff(patched_errand_deps, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    errand = DummyErrand()
    exit_code = errand.run(["--apply", "--preview-dir", str(tmp_path)])

    assert exit_code == 0
    session = FakeSession.instances[-1]
    assert session.mode is Mode.APPLY
    assert [p.name for p in session.fill_calls] == ["Full name", "Email", "Form type"]
    assert session.handoff_calls == [DummyErrand.HANDOFF]
    out = capsys.readouterr().out
    assert f'APPLY handed off at "{DummyErrand.HANDOFF}"' in out
    # NIT 14: fill() only ever receives the FieldPlan (never the resolved
    # value) in this stub, but stdout must still be clean end to end.
    assert RAW_EMAIL_SECRET not in out
    assert RAW_REGISTRY_VALUE not in out


# --- FIX-FIRST 3: pre-resolve now runs before ANY window, in every mode ----


@pytest.mark.parametrize("mode_flags", [[], ["--check"], ["--apply"]], ids=["preview", "check", "apply"])
def test_refuses_before_session_when_secret_missing_in_every_mode(
    patched_errand_deps, tmp_path, monkeypatch, capsys, mode_flags
):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def plan_fn(registry):
        return [FieldPlan(name="Bad", selector="#x", source=parse_source("secret:does-not-exist-item"))]

    errand = DummyErrand(plan_fn=plan_fn)
    exit_code = errand.run([*mode_flags, "--preview-dir", str(tmp_path)])

    assert exit_code == 1
    assert FakeSession.instances == []
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "does-not-exist-item" in out


@pytest.mark.parametrize("mode_flags", [[], ["--check"], ["--apply"]], ids=["preview", "check", "apply"])
def test_refuses_before_session_when_registry_path_missing_in_every_mode(
    patched_errand_deps, tmp_path, monkeypatch, capsys, mode_flags
):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def plan_fn(registry):
        return [FieldPlan(name="Bad", selector="#x", source=parse_source("registry:identity.nonexistent"))]

    errand = DummyErrand(plan_fn=plan_fn)
    exit_code = errand.run([*mode_flags, "--preview-dir", str(tmp_path)])

    assert exit_code == 1
    assert FakeSession.instances == []
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "identity.nonexistent" in out


def test_apply_without_tty_is_refused_exit_1(patched_errand_deps, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    errand = DummyErrand()
    exit_code = errand.run(["--apply", "--preview-dir", str(tmp_path)])

    assert exit_code == 1
    assert FakeSession.instances == []
    out = capsys.readouterr().out
    assert "REFUSED" in out


def test_apply_headless_is_refused_exit_1(patched_errand_deps, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    errand = DummyErrand()
    exit_code = errand.run(["--apply", "--headless", "--preview-dir", str(tmp_path)])

    assert exit_code == 1
    assert FakeSession.instances == []
    out = capsys.readouterr().out
    assert "REFUSED" in out


# --- FIX-FIRST 4: pre-session block also catches plain Exception -----------


def test_malformed_profile_json_is_caught_before_session(patched_errand_deps, wired_vault, tmp_path, capsys):
    wired_vault.put_secret("profile", "{not valid json")

    def plan_fn(registry):
        return [FieldPlan(name="Name", selector="#x", source=parse_source("registry:identity.full_name"))]

    errand = DummyErrand(plan_fn=plan_fn)
    exit_code = errand.run(["--preview-dir", str(tmp_path)])

    assert exit_code == 1
    assert FakeSession.instances == []
    out = capsys.readouterr().out
    assert "ERROR: ProfileError" in out
    assert "not valid JSON" in out


# --- BLOCK 1: an exception from fill() must never leak its raw value -------


def test_fill_exception_with_raw_value_never_reaches_stdout_or_stderr(
    patched_errand_deps, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.delenv("HEADLESS_DEBUG", raising=False)

    class ExplodingFillSession(FakeSession):
        def fill(self, plan, vault, registry):
            # Simulates a raw Playwright-style error whose call log embeds
            # the value just typed - exactly what session.py's FillFailed
            # wrapping exists to prevent from ever reaching this far intact.
            raise RuntimeError(f'Locator.fill: Timeout exceeded.\nCall log:\n  - fill("{RAW_EMAIL_SECRET}")')

    monkeypatch.setattr("headless.errand.Session", ExplodingFillSession)
    errand = DummyErrand()
    exit_code = errand.run(["--apply", "--preview-dir", str(tmp_path)])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert RAW_EMAIL_SECRET not in captured.out
    assert RAW_EMAIL_SECRET not in captured.err
    assert "ERROR: RuntimeError (rerun with HEADLESS_DEBUG=1 for the traceback)" in captured.out


def test_unexpected_post_launch_error_is_exit_2_and_hides_the_message(
    patched_errand_deps, tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("HEADLESS_DEBUG", raising=False)

    class ExplodingSession(FakeSession):
        def goto(self, url):
            raise RuntimeError("simulated site failure")

    monkeypatch.setattr("headless.errand.Session", ExplodingSession)
    errand = DummyErrand()
    exit_code = errand.run(["--preview-dir", str(tmp_path)])

    assert exit_code == 2
    out = capsys.readouterr().out
    assert "ERROR: RuntimeError (rerun with HEADLESS_DEBUG=1 for the traceback)" in out
    # The generic post-launch branch never prints the exception's own
    # message, only its class name - even for a non-secret-bearing error.
    assert "simulated site failure" not in out


def test_headless_debug_env_prints_traceback_to_stderr_only(patched_errand_deps, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HEADLESS_DEBUG", "1")

    class ExplodingSession(FakeSession):
        def goto(self, url):
            raise RuntimeError("simulated site failure")

    monkeypatch.setattr("headless.errand.Session", ExplodingSession)
    errand = DummyErrand()
    exit_code = errand.run(["--preview-dir", str(tmp_path)])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "simulated site failure" not in captured.out
    assert "Traceback" in captured.err
    assert "RuntimeError" in captured.err
