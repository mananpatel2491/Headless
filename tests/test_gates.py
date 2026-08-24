"""Unit tests for headless/gates.py: the preview/apply/check state table from
data-model.md, the mutually exclusive --apply/--check flags, and proof that no
submit/pay/verify/otp/yes/confirm flag exists anywhere in the parser (FR-007).
"""

from __future__ import annotations

import argparse

import pytest

from headless.gates import GateRefused, Mode, add_mode_arguments, resolve_mode


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_mode_arguments(parser)
    return parser


def test_no_flags_is_preview():
    args = make_parser().parse_args([])
    assert resolve_mode(args, isatty=True, headed=True) is Mode.PREVIEW
    assert resolve_mode(args, isatty=False, headed=False) is Mode.PREVIEW


def test_check_flag_is_check_regardless_of_tty_or_headed():
    args = make_parser().parse_args(["--check"])
    assert resolve_mode(args, isatty=False, headed=False) is Mode.CHECK
    assert resolve_mode(args, isatty=True, headed=True) is Mode.CHECK


def test_apply_with_tty_and_headed_is_apply():
    args = make_parser().parse_args(["--apply"])
    assert resolve_mode(args, isatty=True, headed=True) is Mode.APPLY


def test_apply_without_tty_refused():
    args = make_parser().parse_args(["--apply"])
    with pytest.raises(GateRefused, match="interactive terminal"):
        resolve_mode(args, isatty=False, headed=True)


def test_apply_without_headed_refused():
    args = make_parser().parse_args(["--apply"])
    with pytest.raises(GateRefused, match="visible browser"):
        resolve_mode(args, isatty=True, headed=False)


def test_apply_and_check_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        make_parser().parse_args(["--apply", "--check"])


@pytest.mark.parametrize(
    "flag",
    ["--submit", "--pay", "--verify", "--otp", "--yes", "--confirm"],
)
def test_forbidden_flags_do_not_exist(flag):
    with pytest.raises(SystemExit):
        make_parser().parse_args([flag])


def test_mode_has_exactly_three_values():
    assert {m.value for m in Mode} == {"preview", "apply", "check"}
