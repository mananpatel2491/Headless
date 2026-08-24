"""The preview / apply / check gates and the human handoff.

There is no fourth mode and no helper here (or anywhere in this package) ever
accepts a submit, pay, verify, or one-time-code concept (FR-007). Apply refuses
without an interactive terminal or without a visible browser being available
(FR-008); `headed` here is that availability, from `Config.headed`
(`HEADLESS_HEADED` / `--headless`), unchanged by "quiet by default" (v0.0.1):
whether the window is actually shown from launch, versus started
minimized/off-screen and surfaced only at the handoff, is `Config.show` and
is resolved downstream in `headless/session.py`, not here.
"""

from __future__ import annotations

import argparse
from enum import Enum


class Mode(str, Enum):
    PREVIEW = "preview"
    APPLY = "apply"
    CHECK = "check"


class GateRefused(RuntimeError):
    """Raised when a gate refuses to run (missing TTY, headless apply, etc.)."""


def add_mode_arguments(parser: argparse.ArgumentParser) -> None:
    """Wire the shared errand flags onto `parser`.

    Only the flags named in contracts/cli-and-package.md exist here:
    --apply, --check (mutually exclusive), --profile-dir, --headless, --show
    (mutually exclusive), --preview-dir, --no-screenshot. No
    submit/pay/verify/otp/yes/confirm flag is ever added.

    Quiet by default (v0.0.1, Director decision 2026-08-24): preview and
    check run invisibly unless --show; apply always opens a real window (the
    handoff needs one) but starts it minimized/off-screen, surfacing it only
    at the handoff, unless --show. --headless forces invisible and is
    refused together with --apply (unchanged: the handoff needs a window).
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        action="store_true",
        help="Fill the mapped fields up to the handoff, then print 'Your turn'.",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Read-only: report each dependent selector as found or missing.",
    )
    parser.add_argument(
        "--profile-dir",
        dest="profile_dir",
        default=None,
        help="Override HEADLESS_PROFILE_DIR.",
    )
    visibility_group = parser.add_mutually_exclusive_group()
    visibility_group.add_argument(
        "--headless",
        action="store_true",
        help="Force invisible (preview/check only). Refused together with --apply.",
    )
    visibility_group.add_argument(
        "--show",
        action="store_true",
        help="Make the window visible from launch (preview/check), or disable apply's "
        "quiet-until-handoff minimize.",
    )
    parser.add_argument(
        "--preview-dir",
        dest="preview_dir",
        default=None,
        help="Override HEADLESS_PREVIEW_DIR.",
    )
    parser.add_argument(
        "--no-screenshot",
        dest="no_screenshot",
        action="store_true",
        help="Write only the JSON preview artifact; skip the masked screenshot.",
    )


def resolve_mode(args: argparse.Namespace, *, isatty: bool, headed: bool) -> Mode:
    """Resolve the run mode per the data-model.md table. Raises GateRefused."""
    if getattr(args, "check", False):
        return Mode.CHECK
    if getattr(args, "apply", False):
        if not isatty:
            raise GateRefused("apply needs an interactive terminal")
        if not headed:
            raise GateRefused("apply needs a visible browser")
        return Mode.APPLY
    return Mode.PREVIEW
