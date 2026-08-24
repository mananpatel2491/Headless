"""Headless: shared mechanics for the Director's personal browser errand runner.

This package holds the reusable plumbing every errand script composes: non-secret
configuration (config.py), the preview/apply/check gates and the human handoff
(gates.py), the secrets vault seam (secrets.py), the profile registry of typeable
values (profile.py), field plans and redaction (fields.py), redacted preview
artifacts (preview.py), the headed persistent-profile Chrome session (session.py),
and the Errand base class that wires argparse to the run state machine
(errand.py). See CLAUDE.md and specs/001-foundation-errand-runner/ for the rules
this package enforces.
"""

from __future__ import annotations

__version__ = "0.0.1"
