"""The local-model (Ollama) request/response contract (spec
006-policy-extraction-v2, research.md D3, contracts/extraction-v2.md
section 1).

Owns the one HTTP call this feature ever makes: `POST <url>/api/generate`,
with the proven payload shape (`"think": false` is mandatory - omitting it
causes `qwen3.5` to spend its whole token budget on internal reasoning and
return an empty `response` field instead of an error, research.md). The
component that performs the call is an injectable `transport` callable, so
no unit test in this repository ever opens a real socket or reaches a real
Ollama process (spec FR-009) - production wires it to `urllib.request`
(`_default_transport`, below), the standard library only, matching this
feature's own "no dependency this feature does not strictly need"
discipline (research.md D3).

Nothing here knows about `ExtractionCandidate` or any other
`headless/policydoc.py` type: this module's own request/response contract
is a plain-dictionary shape (data-model.md's own "an external HTTP contract
this feature does not own the far side of" rationale) - `headless/
policydoc.py` composes this module, not the other way around.

Every non-success outcome (a connection failure, a missing model, a
timeout, an empty response, a non-JSON response, or a response that does
not match the candidate schema) collapses to one exception,
`LocalModelUnavailable`, whose own message is value-free by construction -
it never carries the prompt, the document text, or the raw response body,
only a short, generic, internal reason (FR-010 through FR-013).

Localhost-only enforcement (FR-007) lives one layer up, in
`headless/config.py`'s own `load_config()` - by the time this module's
`generate_candidate` is ever called, `config.ollama_url` has already been
validated once, at load time (the same precedent `age_file`'s own
`ConfigError` already established). This module does not re-validate the
host itself; it trusts the URL it is given, the same way every other
`headless/` module trusts an already-validated `Config` field.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Callable

OLLAMA_GENERATE_PATH = "/api/generate"

# A bounded timeout, one attempt, no retry loop (spec FR-008). The proven
# local-model round trip (3.3 seconds against a synthetic snippet,
# research.md) is well inside this default - it is a safety bound, not a
# target to optimize toward.
DEFAULT_TIMEOUT = 120.0

# spec 007-extraction-fidelity, FR-032, research.md D7: a conservative
# context-window size common to a locally-hosted mid-size model, added to
# the request's own `options` object so the actual window in effect is
# always explicit rather than left to Ollama's own per-model default (which
# this pipeline has no visibility into and no way to detect a silent
# truncation against). Callers needing a different value for a differently
# configured model pass `num_ctx` explicitly - this constant is only the
# default.
#
# IMPORTANT 5 (Opus verifier, 2026-08-30): raised from 8192 to 16384 -
# `ollama show qwen3.5:35b` (localhost, read-only, run once) reports this
# machine's own configured model at `context length 262144`, well over the
# 16k threshold the orchestrator's own decision names. 16384 remains a
# conservative choice well under the model's own real ceiling, not a claim
# that the model's full window is safe to fill.
DEFAULT_NUM_CTX = 16384

# IMPORTANT 5: num_ctx bounds the model's TOTAL context window - the
# prompt PLUS the response it must still generate inside that same window.
# Comparing the prompt's own estimated length against the raw num_ctx
# value alone would let a prompt that leaves zero room for a response
# still pass this guard unremarked. A fixed reserve is subtracted from
# num_ctx before the comparison; the response itself is JSON, typically
# far smaller than 1024 tokens for this contract's own schema, so this
# reserve is generous, not a tight fit.
DEFAULT_RESPONSE_RESERVE_TOKENS = 1024

# A simple, deterministic estimate (contracts/fidelity.md section 6's own
# example) - never a real tokenizer call. Four characters per token is a
# common rough English-text approximation; this only has to be good enough
# to flag "this document is probably too long for the configured window,"
# never an exact count.
_CHARS_PER_TOKEN_ESTIMATE = 4

Transport = Callable[[str, dict, float], dict]


class LocalModelUnavailable(RuntimeError):
    """Every failure classification in contracts/extraction-v2.md section 1
    collapses to this one exception: a connection failure, a missing-model
    response, a timeout, an empty response field, a non-JSON response, or a
    response that parses but does not match the candidate schema. The
    message is value-free by construction (a short, generic, internal
    reason only) - callers print a fixed, standardized note, never
    `str(exc)`, so nothing this exception carries can ever leak document
    text or model output onto the Director's own terminal."""


def _default_transport(url: str, payload: dict, timeout: float) -> dict:
    """Production wiring: the standard library's `urllib.request`, no new
    dependency for one local POST call (research.md D3). Every unit test in
    this repository supplies its own fake `transport` instead - this
    function is never invoked by the default `pytest -q` suite."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _coerce_string_leaf(value: object) -> str | None:
    """NIT 9 (Opus verifier, 2026-08-29): a local model may emit a JSON
    number for a field this contract otherwise expects as a string
    (`"term_months": 12` instead of `"term_months": "12"`) - Ollama's own
    `"format": "json"` constrains the response to valid JSON, not to this
    contract's own string-typed leaves, so a schema-mismatch failure over a
    field that decoded correctly, just as the wrong JSON type, would be
    needlessly strict. Coerces a JSON number to its string form; a JSON
    string passes through unchanged; anything else (a list, an object,
    `null`, or a boolean) returns `None` - never coerced, since a `bool` is
    a subclass of `int` in Python and silently turning `True`/`False` into
    `"True"`/`"False"` would hide a genuinely wrong-shaped response rather
    than tolerate a merely differently-typed one."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _coerce_string_list(value: object) -> list[str]:
    """spec 007-extraction-fidelity, FR-023, FR-029: a lenient coercion for
    `named_insureds`/`excluded_drivers` - these are additive, text-only
    fields (FR-027), never central to core extraction, so a wrong-shaped
    value degrades to an empty list rather than failing the whole
    candidate the way a core field's own mismatch does."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        coerced = _coerce_string_leaf(item)
        if coerced is not None:
            result.append(coerced)
    return result


def _coerce_label_value_entries(value: object, value_key: str) -> list[dict]:
    """spec 007-extraction-fidelity, FR-022, FR-023, FR-029: a lenient
    coercion for `policy_level_deductibles`/`discounts` (`value_key=
    "value"`) and `fees` (`value_key="amount"`) - each entry needs a `label`
    to be usable at all; a malformed entry (not an object, missing/
    wrong-typed `label`) is skipped rather than failing the whole
    candidate, the same additive-field leniency `_coerce_string_list`
    documents above."""
    if not isinstance(value, list):
        return []
    result: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = _coerce_string_leaf(item.get("label"))
        if label is None:
            continue
        coerced_value = _coerce_string_leaf(item.get(value_key, "")) or ""
        result.append({"label": label, value_key: coerced_value})
    return result


def _coerce_asset(value: object) -> dict:
    """spec 007-extraction-fidelity, FR-023, FR-027: `asset` is either
    `{"address": str}` or `{"vehicle": str, "vin": str}` - both a text-only
    shape (FR-027), never gated as a figure. A wrong-shaped or absent value
    degrades to `{}`, the same additive-field leniency the other new
    fields use."""
    if not isinstance(value, dict):
        return {}
    if "address" in value:
        address = _coerce_string_leaf(value.get("address"))
        return {"address": address} if address is not None else {}
    if "vehicle" in value or "vin" in value:
        vehicle = _coerce_string_leaf(value.get("vehicle", "")) or ""
        vin = _coerce_string_leaf(value.get("vin", "")) or ""
        return {"vehicle": vehicle, "vin": vin}
    return {}


def _normalize_candidate_schema(data: object) -> dict | None:
    """The candidate schema `response` must decode to
    (contracts/extraction-v2.md section 1): a missing top-level key,
    `premium` as a non-object, `coverages` as a non-array, or a coverage
    element missing its own `line` is a mismatch - `None` in every such
    case. `limit`/`deductible`/`premium` on a coverage element default to
    empty when the model omits them - only `line` is a hard per-element
    requirement (contract's own "an array element missing line" wording,
    read literally). Every string-typed leaf is coerced via
    `_coerce_string_leaf` (NIT 9) before this function returns, so its
    caller never has to re-check a leaf's own JSON type again. Returns a
    freshly-built, fully-normalized dict on success (never the caller's own
    `data` object, and never partially normalized) or `None` on any
    mismatch.

    spec 007-extraction-fidelity, FR-029: the ten schema-extension fields
    (`policy_number` through `subtotal`) are read the same lenient way
    `coverages`' own optional per-element fields already are - present and
    well-shaped, they are coerced and passed through; absent or
    wrong-shaped, they default to their own empty shape. None of them can
    fail this function's own overall schema-mismatch outcome (only
    `insurer`/`premium`/`coverages` - spec 006's own three core fields -
    can do that), since a real declarations page routinely omits several of
    them and that omission is never itself a sign of a bad response."""
    if not isinstance(data, dict):
        return None
    insurer = _coerce_string_leaf(data.get("insurer"))
    if insurer is None:
        return None
    premium = data.get("premium")
    if not isinstance(premium, dict):
        return None
    term_months = _coerce_string_leaf(premium.get("term_months"))
    amount = _coerce_string_leaf(premium.get("amount"))
    if term_months is None or amount is None:
        return None
    coverages_raw = data.get("coverages")
    if not isinstance(coverages_raw, list):
        return None
    coverages: list[dict] = []
    for coverage in coverages_raw:
        if not isinstance(coverage, dict):
            return None
        line = _coerce_string_leaf(coverage.get("line"))
        if line is None:
            return None
        normalized_coverage = {"line": line}
        for optional_key in ("limit", "deductible", "premium"):
            coerced = _coerce_string_leaf(coverage.get(optional_key, ""))
            if coerced is None:
                return None
            normalized_coverage[optional_key] = coerced
        coverages.append(normalized_coverage)
    return {
        "insurer": insurer,
        "premium": {"term_months": term_months, "amount": amount},
        "coverages": coverages,
        "policy_number": _coerce_string_leaf(data.get("policy_number", "")) or "",
        "effective_date": _coerce_string_leaf(data.get("effective_date", "")) or "",
        "expiration_date": _coerce_string_leaf(data.get("expiration_date", "")) or "",
        "policy_level_deductibles": _coerce_label_value_entries(data.get("policy_level_deductibles"), "value"),
        "asset": _coerce_asset(data.get("asset")),
        "named_insureds": _coerce_string_list(data.get("named_insureds")),
        "excluded_drivers": _coerce_string_list(data.get("excluded_drivers")),
        "discounts": _coerce_label_value_entries(data.get("discounts"), "value"),
        "fees": _coerce_label_value_entries(data.get("fees"), "amount"),
        "subtotal": _coerce_string_leaf(data.get("subtotal", "")) or "",
    }


def estimate_token_count(text: str) -> int:
    """spec 007-extraction-fidelity, FR-032, contracts/fidelity.md section
    6: a simple, deterministic estimate (character count divided by
    `_CHARS_PER_TOKEN_ESTIMATE`) - never a real tokenizer call, and never
    itself a network or model invocation."""
    return len(text or "") // _CHARS_PER_TOKEN_ESTIMATE


def context_window_warning(
    text: str,
    num_ctx: int,
    *,
    response_reserve_tokens: int = DEFAULT_RESPONSE_RESERVE_TOKENS,
) -> str | None:
    """spec 007-extraction-fidelity, FR-032; corrected by IMPORTANT 5 (Opus
    verifier, 2026-08-30): `None` when `text`'s own estimated token count
    (`estimate_token_count`) is within `num_ctx - response_reserve_tokens`;
    otherwise one value-free warning naming only the estimated count and
    the (reserve-adjusted) threshold - never `text` itself, so a caller can
    append it directly to a candidate's own `warnings` list without
    risking document content leaking into it.

    IMPORTANT 5: `text` MUST be the FULL prompt actually sent to the model
    (the caller's own `_build_extraction_prompt(document.text)`, not the
    converted document text alone) - the original design measured only the
    document text, under-counting the request by the prompt template's own
    fixed instructional overhead. The threshold is `num_ctx -
    response_reserve_tokens`, never the raw `num_ctx`, since num_ctx bounds
    the prompt AND the model's own response together, not the prompt
    alone."""
    threshold = max(0, num_ctx - response_reserve_tokens)
    estimated = estimate_token_count(text)
    if estimated <= threshold:
        return None
    return (
        "converted document is long enough that the local model's context "
        f"window may truncate it (an estimated {estimated} tokens against "
        f"a {threshold}-token guard)"
    )


def generate_candidate(
    *,
    model: str,
    url: str,
    prompt: str,
    transport: Transport | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> dict:
    """POSTs the payload contracts/extraction-v2.md section 1 defines
    (`"model"`, `"prompt"`, `"format": "json"`, `"stream": false,
    "think": false`, `"options": {"temperature": 0}`) to
    `<url>/api/generate` via the injectable `transport`, and returns the
    parsed candidate schema dict on success.

    spec 007-extraction-fidelity, FR-032: `options` also carries an
    explicit `num_ctx` (default `DEFAULT_NUM_CTX`) alongside
    `"temperature": 0`, so the request always states its own context
    window rather than leaving it to Ollama's own per-model default.

    Raises `LocalModelUnavailable` for every failure classification the
    contract defines - never a partial or best-effort candidate (FR-010
    through FR-013). `transport` defaults to `_default_transport`
    (`urllib.request`); every test in this repository injects a fake
    instead (FR-009)."""
    transport = transport or _default_transport
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": num_ctx},
    }
    full_url = url.rstrip("/") + OLLAMA_GENERATE_PATH

    try:
        envelope = transport(full_url, payload, timeout)
    except LocalModelUnavailable:
        raise
    except Exception as exc:
        # Connection refused, DNS failure, a "model not installed" HTTP
        # status, or a timeout - every transport-level exception collapses
        # to the same failed-attempt outcome (FR-012, FR-008/FR-013).
        raise LocalModelUnavailable("local model request failed") from exc

    response_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not response_text:
        # The "think"-omitted gotcha's own failure shape (research.md): an
        # empty string, never an error - treated identically whether or not
        # "think": false was actually honored, since a future model or
        # Ollama version could reproduce it independently of that flag
        # (FR-011).
        raise LocalModelUnavailable("empty response")

    try:
        candidate = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LocalModelUnavailable("response was not valid JSON") from exc

    normalized = _normalize_candidate_schema(candidate)
    if normalized is None:
        raise LocalModelUnavailable("response did not match the candidate schema")

    return normalized
