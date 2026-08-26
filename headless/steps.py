"""Step: the walk framework's non-FieldPlan step kinds (spec 005-insurance-quote-comparison).

`FieldPlan` (headless/fields.py, spec 001) is unchanged and remains one kind of `Step`. The
three new kinds below are frozen dataclasses; `Step` is a plain type alias, not a base class -
data-model.md needs no shared runtime behavior beyond "one of these four shapes."

Invariant - order is meaning: a walk's steps execute strictly in the order `Errand.walk()`
returns them (data-model.md); there is no reordering, no parallel execution.

Invariant - no step type here ever types outside the registry/vault/literal path: `ClickStep`
and `HumanStep` carry no typed value at all, and `CaptureStep` only reads. The only step kind
that ever writes a value into a page is `FieldPlan`, unchanged from before this feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from headless.fields import FieldPlan


@dataclass(frozen=True)
class ClickStep:
    """A named wizard-navigation click. Executable only in apply mode
    (`Session.click` refuses outside apply, mirroring `Session.fill`'s own
    guard); no retry on failure. Never targets a purchase, submit, or
    payment control (FR-010) - this delivery's own walks never point one
    there, and no future walk built on this framework may either."""

    name: str
    selector: str


@dataclass(frozen=True)
class HumanStep:
    """A named mid-walk handoff to the Director. Executed through the
    existing `Session.handoff(instruction)` call (FR-003): the walk
    continues to its next step afterward - it does not end there the way
    today's single trailing handoff does."""

    name: str
    instruction: str


@dataclass(frozen=True)
class CaptureStep:
    """A named, read-only scrape of a page into a flat field mapping
    (`extractors`: field key -> CSS selector). Never clicks, never types;
    a missing selector yields an empty string for that one field rather
    than aborting the whole step (FR-005)."""

    name: str
    extractors: dict[str, str]


# A plain union, not a base class: every consumer (Errand.walk()'s dispatch
# loop, the pre-resolution loop) distinguishes kinds by isinstance, exactly
# the way FieldPlan already was the only kind before this feature existed.
Step = Union[FieldPlan, ClickStep, HumanStep, CaptureStep]
