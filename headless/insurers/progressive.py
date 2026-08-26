"""Progressive auto insurance quote walk (spec 005-insurance-quote-comparison,
User Story 2). One insurer's `Errand` subclass, composed by
`scripts/quote_compare.py` via `headless.insurers.WALK_REGISTRY`.

Site: https://www.progressive.com/auto/ (public quote-start page - no
login required to reach it).
Reads: nothing beyond the landing page's own selectors.
Writes (up to): the ZIP field and the quote-start click - never past the
landing page in this delivery (see the recon note below).
Secrets / profile fields: `registry:addresses.home.zip`.
Handoff: see HANDOFF below - this walk's own terminal state, not a
browser action to take (nothing further is automated).

Implementation-time recon (research.md D8, FR-032/FR-033/FR-034): at most
three headless, scratch-Chrome-profile walks against the real site,
synthetic ZIP data only ("48000"), never the Director's real identity,
address, date of birth, or licence data, and never a purchase/submit/
payment click at any point. Findings, recorded in full in research.md's own
"Recon results" section:

- The two selectors verified before this feature was scoped (`#zipCode_mma`,
  `#qsButton_mma`) both resolve on the landing page, confirmed again.
- Filling the ZIP field and submitting via a direct click, an Enter
  keypress in the field, and a JS-dispatched click on the same button all
  produced the same outcome across the three walks: three
  "Failed to load resource: the server responded with a status of 403
  (Forbidden)" console errors, and the page never navigated away from
  `https://www.progressive.com/auto/` within a 20-second wait. Progressive's
  own funnel refuses the automated quote-start submission specifically
  under headless Chrome (recorded as evidence for the repository's standing
  headless-user-agent question, `PATTERNS.md`'s "Quiet by default" entry -
  see research.md D8's own recon results section).
- No page past the landing page was ever reached in any of the three
  walks, so no further selector (an "are you currently insured?" question,
  a coverage-package/tier page, a quote page) could be proven. None ships:
  FR-032's "no selector beyond the landing page ships unless recon proves
  it resolves" rule is exact here, and there is no known "next step" to
  bridge with a `HumanStep` either, since recon never got far enough to
  learn what one would even instruct the Director to do next.

This walk therefore ships exactly the two pre-verified landing steps and
nothing more. `HANDOFF` explains the situation to the Director rather than
guessing at what comes next; a real `--apply` run (which always launches a
real, non-headless windowed Chrome per `CLAUDE.md`'s "quiet by default"
rule, not Chrome's headless rendering mode) may or may not hit the same
block - that is unverified either way, since this delivery's own recon
authorization is headless-only (D8) and this walk never ships a step past
what recon actually proved.
"""

from __future__ import annotations

from headless.errand import Errand
from headless.fields import FieldPlan, parse_source
from headless.steps import ClickStep

HANDOFF = (
    "review the report; nothing further is automated here. Implementation-time recon "
    "could not verify any step past this quote-start click - Progressive's own funnel "
    "returned HTTP 403 on the quote-start submission under headless Chrome during recon "
    "(research.md D8) - so no further selector ships. Continue the quote by hand in this "
    "window if you want to see the live funnel; it is not required."
)


class ProgressiveQuoteErrand(Errand):
    name = "progressive"
    HANDOFF = HANDOFF
    dependencies = ["#zipCode_mma", "#qsButton_mma"]
    # Never proven: recon never reached a coverage-tier page (see the
    # module docstring). None is the documented "no tiering ever observed"
    # value (spec FR-014) - not "no tiering exists", which recon never had
    # the chance to determine either way.
    package = None

    def url(self, args) -> str:
        return "https://www.progressive.com/auto/"

    def plan(self, registry) -> list[FieldPlan]:
        return [
            FieldPlan(
                name="ZIP code",
                selector="#zipCode_mma",
                source=parse_source("registry:addresses.home.zip"),
            ),
        ]

    def walk(self, registry) -> list:
        return [*self.plan(registry), ClickStep(name="Start quote", selector="#qsButton_mma")]
