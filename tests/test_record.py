"""Unit tests for headless/record.py (spec 007-record-scaffold): the flatten
and match table, the event-to-step rules, the terminal-click and skip
invariants, the value-free JSON artifact, and the generated draft - including
that a recorded raw value can never appear in either output.

No browser here: `WalkRecording.add_event` is fed the same dict shapes the
init script's binding delivers. The browser-driving half of the feature is
covered by tests/test_record_browser.py (opt-in, HEADLESS_TEST_BROWSER=1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from headless.fields import FieldPlan
from headless.record import (
    INIT_SCRIPT,
    RecordedClick,
    RecordedField,
    RecordedNav,
    WalkRecording,
    flatten_registry,
    generate_draft,
    match_value,
    to_walk_json,
    validate_errand_name,
)
from headless.steps import ClickStep

REPO_ROOT = Path(__file__).resolve().parent.parent

PROFILE_DOC = {
    "identity": {"full_name": "Test Testerson", "pan": "ABCDE1234F"},
    "addresses": [
        {"type": "home", "line1": "1 Example Street", "zip": "00000"},
        {"type": "work", "line1": "2 Example Street"},
        {"line1": "no type field - never addressable"},
        {"type": "dup", "line1": "first"},
        {"type": "dup", "line1": "second"},
    ],
    "empty": "",
    "count": 2,
}


def _flat() -> list[tuple[str, str]]:
    return flatten_registry(PROFILE_DOC)


def _change(selector: str, value: str = "", *, tag: str = "input", input_type: str = "text",
            label: str = "", name: str = "", elem_id: str = "", autocomplete: str = "",
            password: bool = False, checked: bool | None = None) -> dict:
    return {
        "type": "change", "selector": selector, "tag": tag, "inputType": input_type,
        "name": name, "id": elem_id, "label": label, "autocomplete": autocomplete,
        "password": password, "checked": checked, "value": value,
    }


def _click(selector: str, text: str) -> dict:
    return {"type": "click", "selector": selector, "text": text}


# --- flatten_registry / match_value ---------------------------------------


def test_flatten_scalars_and_nested_dicts():
    flat = dict(_flat())
    assert flat["identity.full_name"] == "Test Testerson"
    assert flat["count"] == "2"


def test_flatten_type_discriminated_arrays():
    flat = dict(_flat())
    assert flat["addresses.home.line1"] == "1 Example Street"
    assert flat["addresses.work.line1"] == "2 Example Street"


def test_flatten_skips_untyped_duplicate_and_empty():
    paths = [path for path, _ in _flat()]
    assert not any("no type" in path for path in paths)
    assert not any(path.startswith("addresses.dup") for path in paths)
    assert "empty" not in paths


def test_match_value_exact_strip_and_order():
    flat = _flat()
    assert match_value("  Test Testerson ", flat) == ["identity.full_name"]
    assert match_value("", flat) == []
    assert match_value("nowhere", flat) == []


def test_match_value_multiple_paths():
    flat = flatten_registry({"a": "same", "b": {"c": "same"}})
    assert match_value("same", flat) == ["a", "b.c"]


# --- WalkRecording rules ---------------------------------------------------


def test_matched_field_becomes_registry_source_and_value_is_gone():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#full_name", "Test Testerson", label="Full name"))
    (step,) = rec.field_steps()
    assert step.source_ref == "registry:identity.full_name"
    assert step.matched and step.kind == "fill" and step.name == "Full name"


def test_unmatched_field_becomes_literal_todo():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#street", "5 Unknown Road"))
    (step,) = rec.field_steps()
    assert step.source_ref == "literal:" and not step.matched


def test_multiple_matches_keep_first_and_list_alternatives():
    rec = WalkRecording("https://example.test/", flatten_registry({"a": "same", "b": {"c": "same"}}))
    rec.add_event(_change("#x", "same"))
    (step,) = rec.field_steps()
    assert step.source_ref == "registry:a" and step.alternatives == ["b.c"]


def test_select_and_checkbox_kinds():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_change("#tier", "plus", tag="select", input_type="select"))
    rec.add_event(_change("#paperless", input_type="checkbox", checked=True))
    rec.add_event(_change("#calls", input_type="checkbox", checked=False))
    tier, paperless, calls = rec.field_steps()
    assert tier.kind == "select"
    assert (paperless.kind, paperless.source_ref) == ("check", "literal:true")
    assert (calls.kind, calls.source_ref) == ("check", "literal:false")


def test_password_and_otp_fields_are_skipped_not_scaffolded():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_change("#pw", password=True, input_type="password"))
    rec.add_event(_change("#pw", password=True, input_type="password"))
    rec.add_event(_change("#code", autocomplete="one-time-code"))
    rec.add_event(_change("#code2", name="login_otp"))
    rec.add_event(_change("#code3", label="Verification code"))
    assert rec.field_steps() == []
    assert [(s.selector, s.reason) for s in rec.skipped] == [
        ("#pw", "password"), ("#code", "otp"), ("#code2", "otp"), ("#code3", "otp"),
    ]


def test_last_change_wins_but_keeps_position():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#a", "first try"))
    rec.add_event(_click("#next", "Continue"))
    rec.add_event(_change("#a", "Test Testerson"))
    field, click = rec.steps
    assert isinstance(field, RecordedField) and field.source_ref == "registry:identity.full_name"
    assert isinstance(click, RecordedClick)


def test_terminal_click_sets_handoff_truncates_and_is_not_a_step():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_change("#a", "x"))
    rec.add_event(_click("#pay", "Pay now"))
    rec.add_event(_change("#b", "y"))
    rec.add_event(_click("#next", "Continue"))
    assert rec.handoff_label == "Pay now"
    assert rec.terminal_reached
    assert len(rec.field_steps()) == 1 and rec.click_steps() == []


@pytest.mark.parametrize("text", ["Submit", "Confirm booking", "e-Verify", "Enter OTP",
                                  "One time password", "Place order", "Checkout"])
def test_terminal_texts_detected(text):
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_click("#x", text))
    assert rec.terminal_reached


def test_continue_style_click_is_recorded():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_click("#continue", "Continue"))
    (click,) = rec.click_steps()
    assert click.name == "Continue" and click.selector == "#continue"


def test_nav_events_dedupe_consecutive():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event({"type": "nav", "url": "https://example.test/step2"})
    rec.add_event({"type": "nav", "url": "https://example.test/step2"})
    rec.add_event({"type": "nav", "url": "https://example.test/step3"})
    navs = [s for s in rec.steps if isinstance(s, RecordedNav)]
    assert [n.url for n in navs] == ["https://example.test/step2", "https://example.test/step3"]


def test_dependencies_are_unique_and_ordered():
    rec = WalkRecording("https://example.test/", [])
    rec.add_event(_change("#a", "x"))
    rec.add_event(_click("#next", "Continue"))
    rec.add_event(_change("#a", "y"))
    assert rec.dependencies() == ["#a", "#next"]


# --- artifacts are value-free ---------------------------------------------


def test_walk_json_never_contains_recorded_values():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#full_name", "Test Testerson", label="Full name"))
    rec.add_event(_change("#street", "5 Unknown Road"))
    payload = to_walk_json(rec, "acme-quote")
    assert "Test Testerson" not in payload
    assert "5 Unknown Road" not in payload
    assert "registry:identity.full_name" in payload
    assert '"schema_version": 1' in payload


def test_draft_never_contains_recorded_values():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#full_name", "Test Testerson", label="Full name"))
    rec.add_event(_change("#street", "5 Unknown Road"))
    rec.add_event(_change("#pw", password=True, input_type="password"))
    source = generate_draft(rec, "acme-quote")
    assert "Test Testerson" not in source
    assert "5 Unknown Road" not in source


# --- generated draft -------------------------------------------------------


def _record_full_walk() -> WalkRecording:
    rec = WalkRecording("https://example.test/start", _flat())
    rec.add_event(_change("#full_name", "Test Testerson", label="Full name"))
    rec.add_event(_change("#street", "5 Unknown Road", label="Street"))
    rec.add_event(_change("#tier", "plus", tag="select", input_type="select", label="Plan tier"))
    rec.add_event(_change("#paperless", input_type="checkbox", checked=True, label="Paperless"))
    rec.add_event(_click("#continue", "Continue"))
    rec.add_event({"type": "nav", "url": "https://example.test/step2"})
    rec.add_event(_change("#pw", password=True, input_type="password"))
    rec.add_event(_click("#pay", "Pay now"))
    return rec


def _exec_draft(source: str) -> dict:
    namespace = {"__file__": str(REPO_ROOT / "scripts" / "generated-draft.py"), "__name__": "draft"}
    exec(compile(source, "generated-draft.py", "exec"), namespace)
    return namespace


def test_draft_compiles_and_builds_a_real_errand():
    source = generate_draft(_record_full_walk(), "acme-quote")
    namespace = _exec_draft(source)
    errand_class = namespace["AcmeQuoteErrand"]
    errand = errand_class()
    assert errand.name == "acme-quote"
    assert "Pay now" in errand.HANDOFF
    assert errand.url(None) == "https://example.test/start"
    steps = errand.walk(None)
    kinds = [type(step).__name__ for step in steps]
    assert kinds == ["FieldPlan", "FieldPlan", "FieldPlan", "FieldPlan", "ClickStep"]
    full_name, street, tier, paperless = [s for s in steps if isinstance(s, FieldPlan)]
    assert full_name.source.kind == "registry" and full_name.source.ref == "identity.full_name"
    assert street.source.kind == "literal" and street.source.ref == ""
    assert tier.kind == "select"
    assert (paperless.kind, paperless.source.ref) == ("check", "true")
    (click,) = [s for s in steps if isinstance(s, ClickStep)]
    assert click.selector == "#continue"
    assert errand.dependencies == ["#full_name", "#street", "#tier", "#paperless", "#continue"]


def test_draft_marks_todos_skips_and_navs():
    source = generate_draft(_record_full_walk(), "acme-quote")
    assert "TODO: no registry match" in source
    assert "# arrived: https://example.test/step2" in source
    assert "#pw" in source and "login seeding stays human" in source
    # Two unresolved sources: #street (no match) and #tier (the selected
    # option's value is not a registry scalar either).
    assert source.splitlines()[1].startswith("# NOTE: 2 field(s)")


def test_draft_without_terminal_click_has_todo_handoff():
    rec = WalkRecording("https://example.test/", _flat())
    rec.add_event(_change("#full_name", "Test Testerson"))
    source = generate_draft(rec, "acme-quote")
    namespace = _exec_draft(source)
    assert namespace["AcmeQuoteErrand"]().HANDOFF.startswith("TODO:")


def test_errand_name_validation():
    validate_errand_name("acme-quote-2")
    for bad in ("Acme", "1st", "has space", "has_underscore", ""):
        with pytest.raises(ValueError):
            validate_errand_name(bad)


# --- init script invariants (string-level; behavior is browser-tested) -----


def test_init_script_guards_and_never_sends_password_values():
    assert "__headlessRecorderInstalled" in INIT_SCRIPT
    assert "_headlessRecordEvent" in INIT_SCRIPT
    # The password branch must send the flag and leave `value` empty: the
    # only assignment to payload.value is behind the !isPassword guard.
    assert INIT_SCRIPT.count("payload.value = String(el.value)") == 1
    assert "!isPassword" in INIT_SCRIPT
