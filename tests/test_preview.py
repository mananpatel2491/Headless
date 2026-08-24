"""Unit tests for headless/preview.py: the masking invariant (no raw registry or
secret value can survive into the JSON dump, D6/FR-010/SC-002) and artifact
naming/creation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from headless.preview import PreviewRecord, write_artifacts

RAW_PAN = "ABCDE1234F"
RAW_SECRET = "hunter2-super-secret"


def _record_with_mixed_fields() -> PreviewRecord:
    return PreviewRecord(
        errand="probe",
        mode="preview",
        url="https://example.com/",
        title="Example Domain",
        handoff="n/a (read-only errand)",
        fields=[
            {"name": "PAN", "selector": "#pan", "source_kind": "registry", "value": RAW_PAN},
            {"name": "Email password", "selector": "#pw", "source_kind": "secret", "value": RAW_SECRET},
            {"name": "Form type", "selector": "#form_type", "source_kind": "literal", "value": "ITR-2"},
        ],
        checks=[{"selector": "#pan", "found": True}],
    )


def test_registry_and_secret_values_are_masked():
    record = _record_with_mixed_fields()
    dump = record.to_json()
    assert RAW_PAN not in dump
    assert RAW_SECRET not in dump
    payload = json.loads(dump)
    pan_field = next(f for f in payload["fields"] if f["name"] == "PAN")
    assert pan_field["value_masked"] == "****4F"
    secret_field = next(f for f in payload["fields"] if f["name"] == "Email password")
    assert secret_field["value_masked"] == "****et"


def test_literal_values_pass_through_unmasked():
    record = _record_with_mixed_fields()
    payload = json.loads(record.to_json())
    literal_field = next(f for f in payload["fields"] if f["name"] == "Form type")
    assert literal_field["value_masked"] == "ITR-2"


def test_no_raw_value_field_in_schema():
    record = _record_with_mixed_fields()
    payload = json.loads(record.to_json())
    for entry in payload["fields"]:
        assert "value" not in entry
        assert set(entry.keys()) == {"name", "selector", "source_kind", "value_masked"}


def test_checks_present_in_schema():
    record = _record_with_mixed_fields()
    payload = json.loads(record.to_json())
    assert payload["checks"] == [{"selector": "#pan", "found": True}]


def test_timestamp_format():
    record = _record_with_mixed_fields()
    assert re.fullmatch(r"\d{8}T\d{6}Z", record.timestamp_utc)


def test_write_artifacts_names_and_creates_dir(tmp_preview_dir: Path):
    record = _record_with_mixed_fields()
    assert not tmp_preview_dir.exists()

    png_path, json_path = write_artifacts(record, b"fake-png-bytes", tmp_preview_dir)

    assert tmp_preview_dir.exists()
    assert png_path == tmp_preview_dir / f"probe-{record.timestamp_utc}.png"
    assert json_path == tmp_preview_dir / f"probe-{record.timestamp_utc}.json"
    assert png_path.read_bytes() == b"fake-png-bytes"
    assert RAW_PAN not in json_path.read_text(encoding="utf-8")
    assert RAW_SECRET not in json_path.read_text(encoding="utf-8")
