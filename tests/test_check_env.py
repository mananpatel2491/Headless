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


# --- T015 (spec 003-login-persistence): chromium_sandbox launch-kwargs -----


class _FakeChromiumForBrowserCheck:
    def __init__(self):
        self.launch_calls: list[dict] = []

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return _FakeBrowserForBrowserCheck()


class _FakeBrowserForBrowserCheck:
    def close(self) -> None:
        pass


class _FakeSyncPlaywrightCtxForBrowserCheck:
    """Stands in for what `sync_playwright()` returns, used as
    `with sync_playwright() as p:` (the exact shape _check_browser() uses)."""

    def __init__(self, playwright_obj):
        self._playwright_obj = playwright_obj

    def __enter__(self):
        return self._playwright_obj

    def __exit__(self, *exc_info):
        return False


def test_check_browser_passes_chromium_sandbox_true(monkeypatch):
    fake_chromium = _FakeChromiumForBrowserCheck()

    class _FakePlaywrightObj:
        chromium = fake_chromium

    fake_ctx = _FakeSyncPlaywrightCtxForBrowserCheck(_FakePlaywrightObj())
    # _check_browser() imports sync_playwright locally from playwright.sync_api
    # at call time, so patching the attribute on that module is the seam.
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: fake_ctx)

    status, hint = check_env._check_browser()

    assert status == "PASS"
    assert hint == ""
    assert len(fake_chromium.launch_calls) == 1
    assert fake_chromium.launch_calls[0]["chromium_sandbox"] is True


# --- T016 (spec 004-age-vault): check_env's vault row, age backend --------


def _age_config(tmp_path, **extra_overrides):
    from headless.config import load_config

    overrides = {"secrets_backend": "age", "age_file": str(tmp_path / "vault.age")}
    overrides.update(extra_overrides)
    return load_config(overrides=overrides)


def test_check_vault_age_pass_when_age_and_file_present(monkeypatch, tmp_path):
    # FR-015 / US3-AS1: on PASS the hint names the active backend.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    config = _age_config(tmp_path)

    monkeypatch.setattr(check_env.shutil, "which", lambda name: "/opt/homebrew/bin/age")

    status, hint = check_env._check_vault(config)
    assert status == "PASS"
    assert hint == "age backend"


def test_check_vault_age_fail_hint_is_platform_aware_darwin(monkeypatch, tmp_path):
    # NIT 9: the FAIL hint for a missing `age` binary names the
    # platform-appropriate install command, not a hardcoded macOS one.
    config = _age_config(tmp_path)
    monkeypatch.setattr(check_env.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_env.sys, "platform", "darwin")

    status, hint = check_env._check_vault(config)
    assert status == "FAIL"
    assert hint == "brew install age"


def test_check_vault_age_fail_hint_is_platform_aware_windows(monkeypatch, tmp_path):
    config = _age_config(tmp_path)
    monkeypatch.setattr(check_env.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_env.sys, "platform", "win32")

    status, hint = check_env._check_vault(config)
    assert status == "FAIL"
    assert hint == "winget install FiloSottile.age"


def test_check_vault_age_fail_hint_is_platform_aware_other(monkeypatch, tmp_path):
    config = _age_config(tmp_path)
    monkeypatch.setattr(check_env.shutil, "which", lambda name: None)
    monkeypatch.setattr(check_env.sys, "platform", "linux")

    status, hint = check_env._check_vault(config)
    assert status == "FAIL"
    assert hint == "install age from your package manager"


def test_check_vault_age_fail_when_vault_file_missing(monkeypatch, tmp_path):
    config = _age_config(tmp_path)
    monkeypatch.setattr(check_env.shutil, "which", lambda name: "/opt/homebrew/bin/age")

    status, hint = check_env._check_vault(config)
    assert status == "FAIL"
    assert "python scripts/vault.py init" in hint


def test_check_vault_age_never_invokes_a_subprocess(monkeypatch, tmp_path):
    # SC-006 / D7: the age backend's vault row never decrypts and never
    # prompts - proven here by making any subprocess call a hard failure.
    vault_file = tmp_path / "vault.age"
    vault_file.write_text("placeholder-ciphertext", encoding="utf-8")
    config = _age_config(tmp_path)

    def fail_run(*args, **kwargs):
        raise AssertionError("check_env's vault row must never invoke a subprocess for the age backend")

    monkeypatch.setattr(check_env.subprocess, "run", fail_run)
    monkeypatch.setattr(check_env.shutil, "which", lambda name: "/opt/homebrew/bin/age")

    status, hint = check_env._check_vault(config)
    assert status == "PASS"


# --- FIX-FIRST 5 (v0.0.4 verifier pass): _print_row appends any non-empty hint


def test_print_row_pass_with_empty_hint_prints_no_suffix(capsys):
    check_env._print_row("browser", "PASS", "")
    out = capsys.readouterr().out
    assert out == "browser      PASS\n"
    assert " - " not in out


def test_print_row_pass_with_hint_appends_it(capsys):
    # FIX-FIRST 5: unlike before, a PASS row now still shows a non-empty
    # hint (e.g. the age backend's "age backend" annotation).
    check_env._print_row("vault", "PASS", "age backend")
    out = capsys.readouterr().out
    assert out == "vault        PASS - age backend\n"


def test_print_row_fail_with_hint_appends_it(capsys):
    check_env._print_row("vault", "FAIL", "brew install age")
    out = capsys.readouterr().out
    assert out == "vault        FAIL - brew install age\n"
