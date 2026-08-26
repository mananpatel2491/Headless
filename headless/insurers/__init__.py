"""The code-level walk registry (spec 005-insurance-quote-comparison,
research.md D1). Exactly one entry in this delivery, `"progressive"`; every
additional insurer is its own future spec. `scripts/quote_compare.py` is the
only reader of this dict - an insurer id present in the Director's
`feature_configs.insurance.companies` list with no entry here produces a
"not mapped yet" report row and triggers zero `Session`/`Config`/
browser-process construction for that id (spec FR-027).
"""

from __future__ import annotations

from headless.errand import Errand
from headless.insurers.progressive import ProgressiveQuoteErrand

WALK_REGISTRY: dict[str, type[Errand]] = {
    "progressive": ProgressiveQuoteErrand,
}
