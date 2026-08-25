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


def test_git_hooks_row_registered():
    # specs/002-commit-safety-gate: a fifth row proves the local pre-commit
    # refusal is actually active on this clone (core.hooksPath is a
    # per-clone setting a tracked file cannot activate on its own).
    assert "git_hooks" in check_env.ROW_NAMES


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_check_git_hooks_pass_when_hookspath_set(monkeypatch):
    def fake_run(args, **kwargs):
        assert args[:3] == ["git", "config", "core.hooksPath"]
        return _FakeCompletedProcess(0, stdout=".githooks\n")

    monkeypatch.setattr(check_env.subprocess, "run", fake_run)
    status, hint = check_env._check_git_hooks()
    assert status == "PASS"
    assert hint == ""


def test_check_git_hooks_fail_when_unset(monkeypatch):
    def fake_run(args, **kwargs):
        return _FakeCompletedProcess(1, stdout="")

    monkeypatch.setattr(check_env.subprocess, "run", fake_run)
    status, hint = check_env._check_git_hooks()
    assert status == "FAIL"
    assert "git config core.hooksPath .githooks" in hint


def test_check_git_hooks_fail_when_pointed_elsewhere(monkeypatch):
    def fake_run(args, **kwargs):
        return _FakeCompletedProcess(0, stdout="some/other/hooks\n")

    monkeypatch.setattr(check_env.subprocess, "run", fake_run)
    status, hint = check_env._check_git_hooks()
    assert status == "FAIL"
    assert "git config core.hooksPath .githooks" in hint


def test_check_git_hooks_fail_when_git_missing(monkeypatch):
    def fake_run(args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(check_env.subprocess, "run", fake_run)
    status, hint = check_env._check_git_hooks()
    assert status == "FAIL"
    assert "git config core.hooksPath .githooks" in hint
