"""Opt-in browser integration test for the recorder observer (spec
007-record-scaffold): proves INIT_SCRIPT plus the exposed binding turn real
DOM interactions on the local recorder fixture into the event shapes
WalkRecording consumes, and that the whole pipe ends in a compilable draft.
Skipped unless HEADLESS_TEST_BROWSER=1, so the default commit gate stays
fast, same as tests/test_gates_browser.py.

The test drives the page with Playwright's own fill/select/check/click - a
stand-in for the Director's hands. That is the OBSERVED side of recording:
nothing here goes through Session.fill or Session.click, and the recorder
itself still never types or clicks anything.

The fixture is a local file that cannot change under us; its password value
is `hunter2-XY`, the repository's own allowlisted synthetic secret
(.scanignore), asserted below to never leave the page.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from playwright.sync_api import sync_playwright

from headless.record import INIT_SCRIPT, WalkRecording, flatten_registry, generate_draft, to_walk_json

pytestmark = pytest.mark.skipif(
    os.environ.get("HEADLESS_TEST_BROWSER") != "1",
    reason="opt-in browser-driving test; set HEADLESS_TEST_BROWSER=1 to run",
)

FIXTURE_URL = (Path(__file__).resolve().parent / "fixtures" / "record.html").as_uri()

PROFILE_DOC = {"identity": {"full_name": "Test Testerson"}}


def _record_fixture_walk() -> tuple[WalkRecording, list[str]]:
    """Drive the fixture once while the observer records; returns the
    recording plus every raw payload string the binding delivered (so the
    test can assert what never crossed the boundary)."""
    recording = WalkRecording(FIXTURE_URL, flatten_registry(PROFILE_DOC))
    raw_payloads: list[str] = []

    def on_event(_source, payload: str) -> None:
        raw_payloads.append(payload)
        recording.add_event(json.loads(payload))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, chromium_sandbox=True)
        context = browser.new_context()
        context.expose_binding("_headlessRecordEvent", on_event)
        context.add_init_script(INIT_SCRIPT)
        page = context.new_page()
        page.goto(FIXTURE_URL)
        page.fill("#full_name", "Test Testerson")
        page.fill("#street", "5 Unknown Road")
        page.select_option("#plan_tier", "plus")
        page.check("#paperless")
        page.fill("#account_password", "hunter2-XY")
        page.fill("#login_otp", "000111")
        page.click("#continue")
        page.click("#pay")
        page.click("#continue")  # after the terminal click: must be ignored
        page.wait_for_timeout(300)
        context.close()
        browser.close()
    return recording, raw_payloads


def test_observer_records_the_fixture_walk_end_to_end():
    recording, raw_payloads = _record_fixture_walk()

    fields = {step.selector: step for step in recording.field_steps()}
    assert fields["#full_name"].source_ref == "registry:identity.full_name"
    assert fields["#street"].source_ref == "literal:" and not fields["#street"].matched
    assert fields["#plan_tier"].kind == "select"
    assert fields["#paperless"].source_ref == "literal:true"
    assert fields["#full_name"].name == "Full name"

    # The unique-id selector wins for every fixture control.
    assert set(fields) == {"#full_name", "#street", "#plan_tier", "#paperless"}

    # Password and OTP controls were skipped, and the password value never
    # crossed the page boundary in any payload.
    assert {(s.selector, s.reason) for s in recording.skipped} == {
        ("#account_password", "password"), ("#login_otp", "otp"),
    }
    assert all("hunter2-XY" not in payload for payload in raw_payloads)

    # Continue was recorded once; Pay now became the handoff and ended the
    # recording (the second Continue click never landed).
    assert [c.selector for c in recording.click_steps()] == ["#continue"]
    assert recording.handoff_label == "Pay now"

    # The whole pipe ends in value-free artifacts and a compilable draft.
    artifact = to_walk_json(recording, "record-fixture")
    assert "hunter2-XY" not in artifact and "5 Unknown Road" not in artifact
    draft = generate_draft(recording, "record-fixture")
    compile(draft, "record-fixture-draft.py", "exec")
    assert "hunter2-XY" not in draft and "Pay now" in draft
