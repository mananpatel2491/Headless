#!/usr/bin/env python3
"""probe: open a URL in the Headless profile and write a preview artifact.

Background: the first errand every later errand builds on. It proves the
persistent Chrome profile keeps the Director logged in between runs (D2), and
gives a fast way to seed a site's login by hand.

Quiet by default (v0.0.1, Director decision 2026-08-24): plain `probe <url>`
runs invisibly (preview, Chrome's headless mode) - no window opens. `probe
<url> --apply` opens a real window to seed a login, but it starts hidden and
is surfaced (restored, brought to front, focused) only at the handoff
("Your turn" prompt), so the Director sees it only when it is actually his
turn to log in and press Enter; the session is then saved in the profile for
every later run. `probe <url> --show` keeps the window visible throughout
(preview/check) or skips the quiet-until-handoff hiding (apply), for a look
at what's happening as it happens.

Site: any URL the Director passes on the command line.
Reads: the page title and a screenshot.
Writes (up to): nothing on the site; this is a read-only errand.
Secrets / profile fields: none.
Handoff: none (`HANDOFF = "n/a (read-only errand)"`). `--apply` still
performs the handoff with an empty field plan, so the window stays open and
the Director can log in before it closes.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Same convention as the Director's Atlassian toolkit: no packaging step for a
# personal tool, just insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless.errand import Errand
from headless.fields import FieldPlan

HANDOFF = "n/a (read-only errand)"


class ProbeErrand(Errand):
    name = "probe"
    HANDOFF = HANDOFF
    dependencies = ["body"]

    def add_arguments(self, parser) -> None:
        parser.add_argument("url", help="The address to open in the Headless profile.")

    def url(self, args) -> str:
        return args.url

    def plan(self, registry) -> list[FieldPlan]:
        return []


def main(argv: list[str] | None = None) -> int:
    return ProbeErrand().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
