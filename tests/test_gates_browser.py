"""Opt-in browser integration test: proves preview/check/apply on a local
fixture page that cannot change under us (D8, quickstart Scenario 4). Skipped
unless HEADLESS_TEST_BROWSER=1, so the default commit gate stays under 10 s
(SC-005). Drives headless Chrome for speed; the headed requirement for apply
is bypassed only via the explicit allow_headless_apply_for_tests=True
constructor argument named in contracts/cli-and-package.md, never via a flag
reachable from the CLI.

Two layers of coverage: direct-Session tests (construct Session by hand -
kept for apply, since headless-apply needs the explicit test-only bypass) and
FixtureErrand end-to-end tests (drive the real Errand.run() state machine,
argparse and all, for preview and check).
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

from headless.config import Config
from headless.errand import Errand
from headless.fields import FieldPlan, parse_source, resolve_source
from headless.gates import Mode
from headless.preview import PreviewRecord, write_artifacts
from headless.profile import ProfileRegistry
from headless.session import Session, _SCREENSHOT_MASK_CSS

pytestmark = pytest.mark.skipif(
    os.environ.get("HEADLESS_TEST_BROWSER") != "1",
    reason="opt-in browser-driving test; set HEADLESS_TEST_BROWSER=1 to run",
)

HANDOFF = "n/a (test fixture)"
DEPENDENCIES = ["#full_name", "#pan", "#email", "#form_type", "#does-not-exist"]


def _fixture_plan() -> list[FieldPlan]:
    return [
        FieldPlan(name="Full name", selector="#full_name", source=parse_source("registry:identity.full_name")),
        FieldPlan(name="PAN", selector="#pan", source=parse_source("registry:identity.pan")),
        FieldPlan(name="Email", selector="#email", source=parse_source("secret:test-email")),
        FieldPlan(name="Form type", selector="#form_type", source=parse_source("literal:ITR-2"), kind="select"),
    ]


class FixtureErrand(Errand):
    """A real Errand subclass (not a stub) used to drive Errand.run() end to
    end against the fixture form, for the modes that don't need the
    headless-apply test bypass (preview, check)."""

    name = "fixture-e2e"
    HANDOFF = HANDOFF
    dependencies = DEPENDENCIES

    def add_arguments(self, parser) -> None:
        parser.add_argument("url")

    def url(self, args) -> str:
        return args.url

    def plan(self, registry) -> list[FieldPlan]:
        return _fixture_plan()


class CspProbeErrand(Errand):
    """A read-only errand (empty plan) used only to drive Errand.run()
    against a CSP-restricted fixture page (N1)."""

    name = "csp-probe"
    HANDOFF = "n/a (test fixture)"
    dependencies = []

    def add_arguments(self, parser) -> None:
        parser.add_argument("url")

    def url(self, args) -> str:
        return args.url

    def plan(self, registry) -> list[FieldPlan]:
        return []


@pytest.fixture
def fixture_config(tmp_path):
    return Config(
        profile_dir=tmp_path / "chrome-profile",
        headed=False,
        cdp_url=None,
        secrets_backend="keychain",
        keychain_account="headless-test-unused",
        gcp_project=None,
        age_file=tmp_path / "vault.age",
        preview_dir=tmp_path / "previews",
    )


@pytest.fixture
def wired_vault(fake_vault):
    fake_vault.put_secret(
        "profile",
        json.dumps({"identity": {"full_name": "Director Name", "pan": "ABCDE1234F"}}),
    )
    fake_vault.put_secret("test-email", "director@example.com")
    return fake_vault


# --- Direct-Session tests ---------------------------------------------------


def test_preview_leaves_fixture_form_empty(fixture_config, fixture_form_url):
    with Session(fixture_config, Mode.PREVIEW) as session:
        session.goto(fixture_form_url)
        assert session.page.input_value("#full_name") == ""
        assert session.page.input_value("#pan") == ""
        assert session.page.input_value("#email") == ""


def test_check_reports_found_and_missing(fixture_config, fixture_form_url):
    with Session(fixture_config, Mode.CHECK) as session:
        session.goto(fixture_form_url)
        results = dict(session.probe(DEPENDENCIES))

    assert results["#does-not-exist"] is False
    for selector in ("#full_name", "#pan", "#email", "#form_type"):
        assert results[selector] is True


def test_apply_fills_mapped_fields_and_never_clicks_submit(fixture_config, wired_vault, fixture_form_url):
    plan = _fixture_plan()
    registry = ProfileRegistry.load(wired_vault)

    with Session(
        fixture_config,
        Mode.APPLY,
        confirm=lambda: None,
        allow_headless_apply_for_tests=True,
    ) as session:
        session.goto(fixture_form_url)
        for field_plan in plan:
            session.fill(field_plan, wired_vault, registry)

        assert session.page.input_value("#full_name") == "Director Name"
        assert session.page.input_value("#pan") == "ABCDE1234F"
        assert session.page.input_value("#email") == "director@example.com"
        assert session.page.input_value("#form_type") == "ITR-2"

        # The submit control was never clicked: the fixture's click handler
        # never fired, so #clicks (set only on click) stays empty.
        clicks_text = session.page.eval_on_selector("#clicks", "el => el.textContent")
        assert clicks_text in ("", None)

        record = PreviewRecord(
            errand="fixture",
            mode=Mode.APPLY.value,
            url=session.page.url,
            title=session.page.title(),
            handoff=HANDOFF,
            fields=[
                {
                    "name": p.name,
                    "selector": p.selector,
                    "source_kind": p.source.kind,
                    "value": resolve_source(p.source, wired_vault, registry),
                }
                for p in plan
            ],
        )
        _png_path, json_path = write_artifacts(record, session.screenshot(), fixture_config.preview_dir)

    dump = json_path.read_text(encoding="utf-8")
    assert "ABCDE1234F" not in dump
    assert "director@example.com" not in dump
    assert "Director Name" not in dump


def test_screenshot_masks_typed_secret_value(fixture_config, wired_vault, fixture_form_url):
    """BLOCK 2a / N2: a cheap way to prove the pre-screenshot mask actually
    changes what's rendered - compare a masked screenshot (Session.screenshot,
    which always injects the mask) against an unmasked one taken directly on
    session.page (exposed for reads) right after typing a real value into
    both an <input> and the [contenteditable] notes div."""
    plan = _fixture_plan()
    notes_plan = FieldPlan(
        name="Notes", selector="#notes", source=parse_source("literal:some sensitive contenteditable notes")
    )
    registry = ProfileRegistry.load(wired_vault)

    with Session(
        fixture_config,
        Mode.APPLY,
        confirm=lambda: None,
        allow_headless_apply_for_tests=True,
    ) as session:
        session.goto(fixture_form_url)
        session.fill(plan[0], wired_vault, registry)  # types "Director Name" into #full_name
        session.fill(notes_plan, wired_vault, registry)  # types into the contenteditable #notes

        masked_png = session.screenshot()
        unmasked_png = session.page.screenshot()
        # N2 / NEW-4: prove the rule itself, not just that some control was masked.
        session.page.add_style_tag(content=_SCREENSHOT_MASK_CSS)
        for sel in ("#notes", "#pan"):
            assert session.page.eval_on_selector(sel, "e => getComputedStyle(e).webkitTextSecurity") == "disc"

    assert masked_png != unmasked_png


def test_screenshot_csp_blocked_mask_falls_back_to_json_only(tmp_path, csp_fixture_url, capsys):
    """N1: a page whose CSP blocks the mask's inline <style> injection must
    never be captured unmasked. Errand.run() must still succeed (exit 0),
    write only the JSON artifact, and print the CSP note."""
    errand = CspProbeErrand()
    exit_code = errand.run(
        [
            "--headless",
            "--profile-dir",
            str(tmp_path / "chrome-profile"),
            "--preview-dir",
            str(tmp_path / "previews"),
            csp_fixture_url,
        ]
    )

    assert exit_code == 0
    previews_dir = tmp_path / "previews"
    json_files = list(previews_dir.glob("*.json"))
    png_files = list(previews_dir.glob("*.png"))
    assert len(json_files) == 1
    assert png_files == []

    out = capsys.readouterr().out
    assert "note: screenshot skipped, the page's CSP blocked the mask" in out
    assert out.strip().splitlines()[-1].startswith("PREVIEW ")


# --- FixtureErrand end-to-end tests (real Errand.run(), real Session) ------


def test_errand_run_end_to_end_preview(tmp_path, wired_vault, fixture_form_url, monkeypatch):
    monkeypatch.setattr("headless.errand.open_vault", lambda config: wired_vault)
    errand = FixtureErrand()
    exit_code = errand.run(
        [
            "--headless",
            "--profile-dir",
            str(tmp_path / "chrome-profile"),
            "--preview-dir",
            str(tmp_path / "previews"),
            fixture_form_url,
        ]
    )

    assert exit_code == 0
    json_files = list((tmp_path / "previews").glob("*.json"))
    assert len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "preview"
    names = {f["name"] for f in payload["fields"]}
    assert names == {"Full name", "PAN", "Email", "Form type"}
    dump = json.dumps(payload)
    assert "ABCDE1234F" not in dump
    assert "director@example.com" not in dump
    assert "Director Name" not in dump


def test_errand_run_end_to_end_check(tmp_path, wired_vault, fixture_form_url, monkeypatch):
    monkeypatch.setattr("headless.errand.open_vault", lambda config: wired_vault)
    errand = FixtureErrand()
    exit_code = errand.run(
        [
            "--check",
            "--headless",
            "--profile-dir",
            str(tmp_path / "chrome-profile"),
            "--preview-dir",
            str(tmp_path / "previews"),
            fixture_form_url,
        ]
    )

    assert exit_code == 0
    json_files = list((tmp_path / "previews").glob("*.json"))
    assert len(json_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "check"
    checks = {c["selector"]: c["found"] for c in payload["checks"]}
    assert checks["#does-not-exist"] is False
    for selector in ("#full_name", "#pan", "#email", "#form_type"):
        assert checks[selector] is True


# --- T012 (spec 003-login-persistence): a document.cookie session cookie ---
# --- survives a Session close and a fresh relaunch on the same profile -----


class _QuietRequestHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler, minus the per-request stderr log line."""

    def log_message(self, format, *args):  # noqa: A002 - matches base signature
        pass


@pytest.fixture
def local_fixture_server():
    """A 127.0.0.1 http.server thread serving tests/fixtures/, so
    document.cookie can set a cookie scoped to a real origin the way
    file:// cannot (research.md D6). No public network involved."""
    directory = str(Path(__file__).resolve().parent / "fixtures")
    handler = functools.partial(_QuietRequestHandler, directory=directory)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_session_cookie_persists_across_relaunch_on_same_profile(tmp_path, local_fixture_server):
    """SC-001, SC-007, quickstart Scenario 5: seed a document.cookie session
    cookie by navigating a launched-profile Session to a local fixture page,
    close it, relaunch a second Session on the same profile directory, and
    confirm the cookie is present before any navigation on the second
    launch - the real-browser proof behind the fake-object tests in
    tests/test_session.py."""
    profile_dir = tmp_path / "chrome-profile"
    config = Config(
        profile_dir=profile_dir,
        headed=False,
        cdp_url=None,
        secrets_backend="keychain",
        keychain_account="headless-test-unused",
        gcp_project=None,
        age_file=tmp_path / "vault.age",
        preview_dir=tmp_path / "previews",
    )
    cookie_url = f"{local_fixture_server}/cookie.html"

    with Session(config, Mode.PREVIEW) as session:
        session.goto(cookie_url)
        cookies_at_close = {c["name"]: c for c in session.context.cookies()}

    assert "sess" in cookies_at_close
    assert cookies_at_close["sess"]["expires"] == -1

    with Session(config, Mode.PREVIEW) as session:
        cookies_after_relaunch = {c["name"]: c for c in session.context.cookies()}

    assert "sess" in cookies_after_relaunch
    assert cookies_after_relaunch["sess"]["value"] == "1"
