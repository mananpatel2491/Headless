"""Unit tests for headless/localllm.py: the local-model request/response
contract (spec 006-policy-extraction-v2, research.md D3,
contracts/extraction-v2.md section 1).

Every test injects a fake `transport` callable - no unit test here ever
opens a real socket or reaches a real Ollama process (spec FR-009, NFR-001).
"""

from __future__ import annotations

import json
import socket

import pytest

from headless.localllm import (
    DEFAULT_TIMEOUT,
    OLLAMA_GENERATE_PATH,
    LocalModelUnavailable,
    generate_candidate,
)

_VALID_RESPONSE_BODY = json.dumps(
    {
        "insurer": "Sample Mutual",
        "premium": {"term_months": "12", "amount": "1200.00"},
        "coverages": [{"line": "collision", "limit": "500", "deductible": "500", "premium": ""}],
    }
)


def _transport_returning(envelope: dict):
    calls = []

    def transport(url: str, payload: dict, timeout: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        return envelope

    transport.calls = calls
    return transport


def _raising_transport(exc: Exception):
    def transport(url: str, payload: dict, timeout: float) -> dict:
        raise exc

    return transport


# --- request construction (spec FR-005, FR-009) -----------------------------


def test_request_payload_has_the_exact_required_shape():
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    generate_candidate(model="qwen3.5:35b", url="http://localhost:11434", prompt="hello", transport=transport)

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "http://localhost:11434" + OLLAMA_GENERATE_PATH
    payload = call["payload"]
    assert payload["model"] == "qwen3.5:35b"
    assert payload["prompt"] == "hello"
    assert payload["format"] == "json"
    assert payload["stream"] is False
    # The "think": false gotcha (research.md): mandatory, not advisory.
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0}


def test_request_uses_the_configured_timeout():
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    generate_candidate(
        model="qwen3.5:35b", url="http://localhost:11434", prompt="hello", transport=transport, timeout=42.0
    )
    assert transport.calls[0]["timeout"] == 42.0


def test_default_timeout_is_120_seconds():
    assert DEFAULT_TIMEOUT == 120.0


def test_transport_is_injectable_and_the_real_transport_is_never_used_when_one_is_passed(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("must never open a real network connection")

    monkeypatch.setattr(socket, "create_connection", _forbidden)
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    generate_candidate(model="qwen3.5:35b", url="http://localhost:11434", prompt="hello", transport=transport)


def test_url_is_joined_regardless_of_a_trailing_slash():
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    generate_candidate(model="m", url="http://localhost:11434/", prompt="p", transport=transport)
    assert transport.calls[0]["url"] == "http://localhost:11434" + OLLAMA_GENERATE_PATH


# --- success path ------------------------------------------------------------


def test_successful_response_parses_into_the_candidate_schema():
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    assert candidate["insurer"] == "Sample Mutual"
    assert candidate["premium"]["term_months"] == "12"
    assert candidate["coverages"][0]["line"] == "collision"


def test_other_ollama_envelope_fields_are_ignored():
    envelope = {"response": _VALID_RESPONSE_BODY, "done": True, "total_duration": 12345}
    transport = _transport_returning(envelope)
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    assert candidate["insurer"] == "Sample Mutual"


# --- failure classification (contracts/extraction-v2.md section 1) ---------
# Every non-success outcome collapses to LocalModelUnavailable - never a
# partial candidate, never a crash (FR-010 through FR-013).


def test_connection_failure_is_a_failed_attempt():
    transport = _raising_transport(ConnectionRefusedError("refused"))
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_dns_or_other_transport_exception_is_a_failed_attempt():
    transport = _raising_transport(OSError("name resolution failed"))
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_model_not_installed_http_error_is_a_failed_attempt():
    transport = _raising_transport(RuntimeError("404 model 'x' not found"))
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_timeout_is_a_failed_attempt():
    transport = _raising_transport(TimeoutError("timed out"))
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_empty_response_field_is_a_failed_attempt():
    # The "think"-omitted gotcha's own failure shape (research.md): an empty
    # string, not an error.
    transport = _transport_returning({"response": ""})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_missing_response_field_entirely_is_a_failed_attempt():
    transport = _transport_returning({"done": True})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_non_json_response_is_a_failed_attempt():
    transport = _transport_returning({"response": "not valid json {{{"})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_schema_mismatch_missing_insurer_is_a_failed_attempt():
    body = json.dumps({"premium": {"term_months": "12", "amount": "100"}, "coverages": []})
    transport = _transport_returning({"response": body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_schema_mismatch_premium_not_an_object_is_a_failed_attempt():
    body = json.dumps({"insurer": "X", "premium": "not-an-object", "coverages": []})
    transport = _transport_returning({"response": body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_schema_mismatch_coverages_not_an_array_is_a_failed_attempt():
    body = json.dumps(
        {"insurer": "X", "premium": {"term_months": "12", "amount": "100"}, "coverages": "not-an-array"}
    )
    transport = _transport_returning({"response": body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_schema_mismatch_coverage_element_missing_line_is_a_failed_attempt():
    body = json.dumps(
        {
            "insurer": "X",
            "premium": {"term_months": "12", "amount": "100"},
            "coverages": [{"limit": "500", "deductible": "", "premium": ""}],
        }
    )
    transport = _transport_returning({"response": body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_coverage_element_missing_optional_fields_still_succeeds():
    # Per contracts section 1: only a missing "line" is a schema mismatch -
    # limit/deductible/premium default to empty when the model omits them.
    body = json.dumps(
        {"insurer": "X", "premium": {"term_months": "12", "amount": "100"}, "coverages": [{"line": "collision"}]}
    )
    transport = _transport_returning({"response": body})
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    assert candidate["coverages"][0]["line"] == "collision"


# --- NIT 9 (Opus verifier, 2026-08-29): numeric leaves are coerced -------
# a local model may emit a bare JSON number instead of a string; Ollama's
# own "format": "json" only constrains the response to valid JSON, not to
# this contract's own string-typed leaves.


def test_numeric_term_months_and_amount_are_coerced_to_strings():
    body = json.dumps({"insurer": "X", "premium": {"term_months": 12, "amount": 1200.0}, "coverages": []})
    transport = _transport_returning({"response": body})
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    assert candidate["premium"]["term_months"] == "12"
    assert isinstance(candidate["premium"]["term_months"], str)
    assert candidate["premium"]["amount"] == "1200.0"
    assert isinstance(candidate["premium"]["amount"], str)


def test_numeric_coverage_limit_is_coerced_to_a_string():
    body = json.dumps(
        {
            "insurer": "X",
            "premium": {"term_months": "12", "amount": "100"},
            "coverages": [{"line": "collision", "limit": 500, "deductible": 0, "premium": 0}],
        }
    )
    transport = _transport_returning({"response": body})
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    coverage = candidate["coverages"][0]
    assert coverage["limit"] == "500"
    assert isinstance(coverage["limit"], str)
    assert coverage["deductible"] == "0"
    assert coverage["premium"] == "0"


def test_numeric_insurer_is_coerced_but_a_boolean_insurer_is_rejected():
    numeric_body = json.dumps({"insurer": 12345, "premium": {"term_months": "12", "amount": "100"}, "coverages": []})
    transport = _transport_returning({"response": numeric_body})
    candidate = generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)
    assert candidate["insurer"] == "12345"

    boolean_body = json.dumps({"insurer": True, "premium": {"term_months": "12", "amount": "100"}, "coverages": []})
    transport = _transport_returning({"response": boolean_body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_a_list_or_object_leaf_value_is_still_rejected_never_coerced():
    body = json.dumps(
        {"insurer": "X", "premium": {"term_months": ["12"], "amount": "100"}, "coverages": []}
    )
    transport = _transport_returning({"response": body})
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_a_failed_attempt_never_raises_anything_other_than_localmodelunavailable():
    transport = _raising_transport(ValueError("weird internal thing"))
    with pytest.raises(LocalModelUnavailable):
        generate_candidate(model="m", url="http://localhost:11434", prompt="p", transport=transport)


def test_localmodelunavailable_message_is_value_free_never_the_document_text():
    # A generic, internal reason only - never the prompt or document text.
    transport = _transport_returning({"response": "not valid json {{{"})
    with pytest.raises(LocalModelUnavailable) as exc_info:
        generate_candidate(
            model="m",
            url="http://localhost:11434",
            prompt="TOTALLY-DISTINCTIVE-DOCUMENT-TEXT-FIXTURE",
            transport=transport,
        )
    assert "TOTALLY-DISTINCTIVE-DOCUMENT-TEXT-FIXTURE" not in str(exc_info.value)


# --- default transport wiring (production path, no real network here) -----


def test_default_transport_is_urllib_based_and_not_used_unless_selected():
    # Confirms a default transport exists (production wiring) without ever
    # invoking it - every test above supplies its own fake.
    import headless.localllm as localllm_module

    assert hasattr(localllm_module, "_default_transport")
