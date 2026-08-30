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
    DEFAULT_NUM_CTX,
    DEFAULT_RESPONSE_RESERVE_TOKENS,
    DEFAULT_TIMEOUT,
    OLLAMA_GENERATE_PATH,
    LocalModelUnavailable,
    context_window_warning,
    estimate_token_count,
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
    # spec 007-extraction-fidelity, FR-032: options now also carries an
    # explicit num_ctx, defaulting to DEFAULT_NUM_CTX when the caller does
    # not override it (amends this same assertion's own spec 006 shape,
    # which never named a context window at all).
    assert payload["options"] == {"temperature": 0, "num_ctx": DEFAULT_NUM_CTX}


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


# --- context-window guard (spec 007-extraction-fidelity, FR-032, D7) ------
# contracts/fidelity.md section 6: an explicit num_ctx on the request, plus
# a simple, deterministic length estimate against it - never a real
# tokenizer, never a refusal (the request is still sent either way).


def test_num_ctx_is_overridable_in_the_request_payload():
    transport = _transport_returning({"response": _VALID_RESPONSE_BODY})
    generate_candidate(
        model="m", url="http://localhost:11434", prompt="p", transport=transport, num_ctx=4096
    )
    assert transport.calls[0]["payload"]["options"] == {"temperature": 0, "num_ctx": 4096}


def test_default_num_ctx_is_a_positive_integer():
    assert isinstance(DEFAULT_NUM_CTX, int)
    assert DEFAULT_NUM_CTX > 0


def test_estimate_token_count_is_a_simple_deterministic_character_based_estimate():
    # Never a real tokenizer call - just proportional to length, and
    # perfectly reproducible for the same input.
    short_estimate = estimate_token_count("a" * 40)
    long_estimate = estimate_token_count("a" * 400)
    assert long_estimate > short_estimate
    assert estimate_token_count("a" * 40) == short_estimate  # deterministic


def test_estimate_token_count_handles_falsy_input():
    assert estimate_token_count("") == 0
    assert estimate_token_count(None) == 0


def test_context_window_warning_is_none_when_the_estimate_is_within_the_threshold():
    short_text = "a" * 40  # estimate well under any reasonable num_ctx
    assert context_window_warning(short_text, num_ctx=1000, response_reserve_tokens=0) is None


def test_context_window_warning_fires_when_the_estimate_exceeds_the_threshold():
    long_text = "a" * 4000
    warning = context_window_warning(long_text, num_ctx=10, response_reserve_tokens=0)
    assert warning is not None
    estimated = estimate_token_count(long_text)
    assert str(estimated) in warning
    assert "10" in warning
    # Value-free (FR-032): names only the estimated count and the
    # threshold, never the document's own content.
    assert "a" * 4000 not in warning


def test_context_window_warning_boundary_is_inclusive_of_exactly_the_reserve_adjusted_threshold():
    text = "a" * 40  # estimate_token_count("a" * 40) == 10 at 4 chars/token
    estimated = estimate_token_count(text)
    assert context_window_warning(text, num_ctx=estimated, response_reserve_tokens=0) is None
    assert context_window_warning(text, num_ctx=estimated - 1, response_reserve_tokens=0) is not None


# --- IMPORTANT 5 (Opus verifier, 2026-08-30): under-measurement fixes ----
# num_ctx must be measured against the FULL prompt (not document text
# alone), and a fixed response reserve must be subtracted from num_ctx
# before comparing - a prompt technically under num_ctx but leaving zero
# room for the model's own response must still be flagged.


def test_context_window_warning_default_reserve_is_subtracted_from_num_ctx():
    # A prompt whose own estimate sits between (num_ctx - reserve) and
    # num_ctx itself must fire - proving the reserve is actually applied,
    # not merely accepted as an unused parameter.
    num_ctx = 2000
    reserve = DEFAULT_RESPONSE_RESERVE_TOKENS
    estimate_between_threshold_and_num_ctx = num_ctx - (reserve // 2)
    text = "a" * (estimate_between_threshold_and_num_ctx * 4)
    warning = context_window_warning(text, num_ctx=num_ctx)
    assert warning is not None
    assert str(num_ctx - reserve) in warning  # the reserve-adjusted threshold, not the raw num_ctx


def test_context_window_warning_default_reserve_value_is_documented():
    assert DEFAULT_RESPONSE_RESERVE_TOKENS == 1024


def test_context_window_warning_never_fires_for_a_real_document_shaped_synthetic_prompt():
    # A synthetic prompt of equivalent length to a real, multi-page
    # declarations page converted to Markdown (several thousand
    # characters) must not spuriously trigger the guard against the
    # default num_ctx/reserve - this is the realistic, common case.
    real_document_shaped_text = "Sample Assurance Mutual Insurance Company. " * 400  # ~17,600 chars
    assert context_window_warning(real_document_shaped_text, num_ctx=DEFAULT_NUM_CTX) is None
