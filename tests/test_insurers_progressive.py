"""Unit tests for headless/insurers/progressive.py: the Progressive walk's
own pure logic (spec 005-insurance-quote-comparison, User Story 2, T020,
T024). Never a real browser call - fixture registry only.

Implementation-time recon (research.md D8, three headless scratch-profile
walks, synthetic ZIP data only) found Progressive's own funnel refuses the
automated quote-start submission under headless Chrome (three "403
Forbidden" resource-load errors, page never navigated past the landing
page). No selector past the landing page was ever proven, so this walk
ships exactly two steps - the FieldPlan and ClickStep already verified
before this feature was scoped - and nothing more (FR-032).
"""

from __future__ import annotations

import ast
from pathlib import Path

from headless.insurers.progressive import ProgressiveQuoteErrand
from headless.steps import CaptureStep, ClickStep, HumanStep
from headless.fields import FieldPlan


class _FakeRegistry:
    def get(self, dotted: str) -> str:
        return "48000"


def test_dependencies_are_exactly_the_two_verified_landing_selectors():
    assert ProgressiveQuoteErrand.dependencies == ["#zipCode_mma", "#qsButton_mma"]


def test_plan_is_the_zip_field_plan_only():
    errand = ProgressiveQuoteErrand()
    plan = errand.plan(_FakeRegistry())
    assert len(plan) == 1
    field_plan = plan[0]
    assert isinstance(field_plan, FieldPlan)
    assert field_plan.selector == "#zipCode_mma"
    assert field_plan.source.kind == "registry"
    assert field_plan.source.ref == "addresses.home.zip"


def test_walk_is_the_zip_field_plan_then_the_quote_start_click():
    errand = ProgressiveQuoteErrand()
    steps = errand.walk(_FakeRegistry())
    assert len(steps) == 2
    assert isinstance(steps[0], FieldPlan)
    assert steps[0].selector == "#zipCode_mma"
    assert isinstance(steps[1], ClickStep)
    assert steps[1].selector == "#qsButton_mma"


def test_walk_ships_no_human_step_or_capture_step_this_delivery():
    # Recon never reached a page past the landing page, so there is no
    # known "next step" to bridge with a HumanStep, and no quote page
    # selector was ever proven to capture (FR-032).
    errand = ProgressiveQuoteErrand()
    steps = errand.walk(_FakeRegistry())
    assert not any(isinstance(s, HumanStep) for s in steps)
    assert not any(isinstance(s, CaptureStep) for s in steps)


def test_url_is_the_progressive_auto_landing_page():
    errand = ProgressiveQuoteErrand()
    assert errand.url(None) == "https://www.progressive.com/auto/"


def test_name_matches_the_walk_registry_key():
    assert ProgressiveQuoteErrand.name == "progressive"


def test_package_is_none_no_tiering_ever_observed():
    assert ProgressiveQuoteErrand.package is None


# --- SC-015: structural absence of the never-wired-this-delivery paths -----


_FORBIDDEN_SUBSTRINGS = (
    "identities.spouse.",
    "addresses.rental.",
    "addresses.work.",
    ".dwelling_type",
)


def test_source_never_references_the_not_yet_wired_registry_paths():
    source_path = Path(__file__).resolve().parent.parent / "headless" / "insurers" / "progressive.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    string_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert not any(forbidden in literal for literal in string_literals), (
            f"{forbidden!r} must never appear in a string literal in progressive.py (spec FR-036)"
        )
