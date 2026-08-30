"""Opt-in integration test for the real local-model seam (spec
006-policy-extraction-v2, NFR-002, research.md).

Gated by `HEADLESS_TEST_OLLAMA=1` - NEVER runs in the default `pytest -q`
suite (the module-level `skipif` below fires before any real network call
is ever attempted), and skips cleanly when the real Ollama server is
unreachable at the configured URL. Runs the real local-model seam against
the wholly synthetic, scrambled-column snippet this feature was scoped
from (`tests/fixtures/declarations-scrambled.txt` - no real policy value,
name, policy number, or premium anywhere in it) and asserts only that the
response parses into the expected candidate schema shape - never an exact
value, since a real model's own wording can vary between runs.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

from headless.config import load_config
from headless.localllm import DEFAULT_TIMEOUT, LocalModelUnavailable, generate_candidate
from headless.policydoc import _build_extraction_prompt

pytestmark = pytest.mark.skipif(
    os.environ.get("HEADLESS_TEST_OLLAMA") != "1",
    reason="opt-in: set HEADLESS_TEST_OLLAMA=1 to run against a real local Ollama server",
)

# Bounded, not the library's own 120s default - this one real round trip is
# allowed up to 240s (research.md's own proven round trip was 3.3s; this is
# a generous ceiling, not a target).
_INTEGRATION_TIMEOUT = 240.0

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SCRAMBLED_DECLARATIONS_TEXT = (FIXTURES_DIR / "declarations-scrambled.txt").read_text(encoding="utf-8")

# NIT 6 (Opus verifier, 2026-08-29): the REAL prompt builder
# (`headless/policydoc.py`'s own `_build_extraction_prompt`), not a
# duplicated copy of its text - so this integration test proves the actual
# production prompt against a real model, and can never silently drift
# from what `generate_candidate_via_local_model` itself sends.
_PROMPT = _build_extraction_prompt(SCRAMBLED_DECLARATIONS_TEXT)

# The one internal LocalModelUnavailable message (headless/localllm.py's
# own `generate_candidate`) that means "the transport call itself could not
# even complete" - a connection-level failure. Every other message
# (`"empty response"`, `"response was not valid JSON"`, `"response did not
# match the candidate schema"`) is a content-level problem with a server we
# already confirmed is reachable, and NIT 6 requires that class to FAIL
# this test, never skip it.
_CONNECTION_LEVEL_FAILURE_MESSAGE = "local model request failed"


def _ollama_reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def test_real_local_model_returns_a_schema_valid_candidate():
    config = load_config()
    if not _ollama_reachable(config.ollama_url):
        pytest.skip(f"Ollama not reachable at {config.ollama_url} - skipping cleanly")

    try:
        candidate = generate_candidate(
            model=config.ollama_model,
            url=config.ollama_url,
            prompt=_PROMPT,
            timeout=min(_INTEGRATION_TIMEOUT, DEFAULT_TIMEOUT * 2),
        )
    except LocalModelUnavailable as exc:
        # NIT 6: skip ONLY for a connection-level failure (the reachability
        # check above can still race a server that drops mid-request);
        # anything else - an empty response, invalid JSON, or a schema
        # mismatch from a server we just proved is up - is a real quality
        # regression worth FAILING on, not silently skipping.
        if str(exc) == _CONNECTION_LEVEL_FAILURE_MESSAGE:
            pytest.skip(f"local model connection failed after a successful reachability check: {exc}")
        raise

    # Schema validity only (NFR-002) - never an exact value.
    assert isinstance(candidate, dict)
    assert isinstance(candidate.get("insurer"), str)
    premium = candidate.get("premium")
    assert isinstance(premium, dict)
    assert isinstance(premium.get("term_months"), str)
    assert isinstance(premium.get("amount"), str)
    coverages = candidate.get("coverages")
    assert isinstance(coverages, list)
    for coverage in coverages:
        assert isinstance(coverage, dict)
        assert isinstance(coverage.get("line"), str)
