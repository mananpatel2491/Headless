"""Unit tests for headless/fields.py: parse_source's three legal source kinds
(and rejection of anything else) and the redact() masking rule.
"""

from __future__ import annotations

import pytest

from headless.fields import FieldPlan, Source, SourceError, parse_source, redact


def test_parse_registry_source():
    source = parse_source("registry:identity.pan")
    assert source == Source(kind="registry", ref="identity.pan")


def test_parse_secret_source():
    source = parse_source("secret:headless-test-secret")
    assert source == Source(kind="secret", ref="headless-test-secret")


def test_parse_literal_source():
    source = parse_source("literal:ITR-2")
    assert source == Source(kind="literal", ref="ITR-2")


@pytest.mark.parametrize("text", ["", "raw-string", "registry", "REGISTRY:x", "env:HOME"])
def test_parse_source_rejects_unknown_prefix(text):
    with pytest.raises(SourceError):
        parse_source(text)


def test_field_plan_holds_a_source():
    plan = FieldPlan(name="PAN", selector="#pan", source=parse_source("registry:identity.pan"))
    assert plan.kind == "fill"
    assert plan.source.kind == "registry"


def test_field_plan_is_frozen():
    plan = FieldPlan(name="PAN", selector="#pan", source=parse_source("literal:x"))
    with pytest.raises(Exception):
        plan.name = "other"


def test_redact_normal_value():
    assert redact("hunter2-XY") == "****XY"


def test_redact_short_value():
    assert redact("ab") == "****"


def test_redact_empty_value():
    assert redact("") == "****"


def test_redact_never_returns_more_than_last_two_chars():
    secret = "super-secret-value-12345"
    masked = redact(secret)
    assert secret not in masked
    assert masked == "****45"
