"""Unit tests for headless/steps.py: the walk framework's non-FieldPlan Step
kinds (spec 005-insurance-quote-comparison, data-model.md).
"""

from __future__ import annotations

import dataclasses

import pytest

from headless.steps import CaptureStep, ClickStep, HumanStep


def test_click_step_constructs_with_documented_fields():
    step = ClickStep(name="Start quote", selector="#qsButton_mma")
    assert step.name == "Start quote"
    assert step.selector == "#qsButton_mma"


def test_human_step_constructs_with_documented_fields():
    step = HumanStep(name="Consent", instruction="Accept the consent screen, then press Enter.")
    assert step.name == "Consent"
    assert step.instruction == "Accept the consent screen, then press Enter."


def test_capture_step_constructs_with_documented_fields():
    step = CaptureStep(name="Quote page", extractors={"premium.amount": "#total"})
    assert step.name == "Quote page"
    assert step.extractors == {"premium.amount": "#total"}


@pytest.mark.parametrize(
    "step",
    [
        ClickStep(name="a", selector="#b"),
        HumanStep(name="a", instruction="b"),
        CaptureStep(name="a", extractors={"x": "#y"}),
    ],
    ids=["click", "human", "capture"],
)
def test_step_kinds_are_frozen(step):
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.name = "changed"


def test_click_step_equality_by_value():
    assert ClickStep(name="a", selector="#b") == ClickStep(name="a", selector="#b")
    assert ClickStep(name="a", selector="#b") != ClickStep(name="a", selector="#c")
