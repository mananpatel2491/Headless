"""Unit test for scripts/check_env.py's minimal argparse layer (FIX-FIRST 8):
check_env takes no flags of its own, but an unknown one (e.g. --submit) must
be refused with a non-zero exit rather than silently ignored.
"""

from __future__ import annotations

import pytest

import scripts.check_env as check_env


def test_unknown_flag_exits_non_zero():
    with pytest.raises(SystemExit) as exc_info:
        check_env.main(["--submit"])
    assert exc_info.value.code != 0
