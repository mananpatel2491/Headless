"""Unit tests for headless/config.py: defaults, ~ expansion, CLI-over-env
precedence, and the ConfigError refusals that must fire before any browser or
vault call (FR-004, SC-006).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from headless.config import Config, ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent

ALL_HEADLESS_VARS = [
    "HEADLESS_PROFILE_DIR",
    "HEADLESS_HEADED",
    "HEADLESS_CDP_URL",
    "HEADLESS_SECRETS_BACKEND",
    "HEADLESS_KEYCHAIN_ACCOUNT",
    "HEADLESS_GCP_PROJECT",
    "HEADLESS_PREVIEW_DIR",
    "HEADLESS_SCREENSHOTS",
    "HEADLESS_SHOW",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL_HEADLESS_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    config = load_config()
    assert isinstance(config, Config)
    assert config.profile_dir == Path("~/.headless/chrome-profile").expanduser()
    assert config.headed is True
    assert config.cdp_url is None
    assert config.secrets_backend == "keychain"
    assert config.keychain_account == "headless"
    assert config.gcp_project is None
    # FIX-FIRST 6: the default resolves against the repo root, not cwd.
    assert config.preview_dir == REPO_ROOT / "previews"
    assert config.screenshots is True
    assert config.show is False


def test_tilde_expansion_from_env(monkeypatch):
    monkeypatch.setenv("HEADLESS_PROFILE_DIR", "~/some-headless-dir")
    config = load_config()
    assert config.profile_dir == Path.home() / "some-headless-dir"
    assert "~" not in str(config.profile_dir)


def test_cli_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("HEADLESS_PROFILE_DIR", "/from-env")
    config = load_config(overrides={"profile_dir": "/from-cli"})
    assert config.profile_dir == Path("/from-cli")


def test_headless_flag_overrides_headed_env(monkeypatch):
    monkeypatch.setenv("HEADLESS_HEADED", "1")
    config = load_config(overrides={"headless": True})
    assert config.headed is False


def test_gcp_backend_without_project_raises(monkeypatch):
    monkeypatch.setenv("HEADLESS_SECRETS_BACKEND", "gcp")
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "HEADLESS_GCP_PROJECT" in str(exc_info.value)


def test_gcp_backend_with_project_ok(monkeypatch):
    monkeypatch.setenv("HEADLESS_SECRETS_BACKEND", "gcp")
    monkeypatch.setenv("HEADLESS_GCP_PROJECT", "my-project")
    config = load_config()
    assert config.secrets_backend == "gcp"
    assert config.gcp_project == "my-project"


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("HEADLESS_SECRETS_BACKEND", "dropbox")
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "HEADLESS_SECRETS_BACKEND" in str(exc_info.value)


def test_preview_dir_absolute_override_is_used_as_is(monkeypatch):
    config = load_config(overrides={"preview_dir": "/tmp/headless-previews-test"})
    assert config.preview_dir == Path("/tmp/headless-previews-test")


def test_preview_dir_relative_override_other_than_default_raises(monkeypatch, tmp_path):
    # N3: a relative --preview-dir/HEADLESS_PREVIEW_DIR other than the
    # literal default "previews" is rejected outright, not silently resolved
    # against the repo root - it could otherwise land anywhere.
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as exc_info:
        load_config(overrides={"preview_dir": "custom-previews"})
    assert "must be absolute or the default 'previews'" in str(exc_info.value)


def test_preview_dir_relative_env_other_than_default_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEADLESS_PREVIEW_DIR", "env-previews")
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "must be absolute or the default 'previews'" in str(exc_info.value)


def test_preview_dir_explicit_default_string_still_resolves_against_repo_root(monkeypatch, tmp_path):
    # The literal default value "previews", even when passed explicitly
    # (not just via absence), is the one relative value still accepted.
    monkeypatch.chdir(tmp_path)
    config = load_config(overrides={"preview_dir": "previews"})
    assert config.preview_dir == REPO_ROOT / "previews"


def test_no_screenshot_override_disables_screenshots(monkeypatch):
    config = load_config(overrides={"screenshots": False})
    assert config.screenshots is False


def test_headless_screenshots_env_flag(monkeypatch):
    monkeypatch.setenv("HEADLESS_SCREENSHOTS", "0")
    config = load_config()
    assert config.screenshots is False


def test_show_defaults_false(monkeypatch):
    config = load_config()
    assert config.show is False


def test_show_override_true(monkeypatch):
    config = load_config(overrides={"show": True})
    assert config.show is True


def test_headless_show_env_flag(monkeypatch):
    monkeypatch.setenv("HEADLESS_SHOW", "1")
    config = load_config()
    assert config.show is True


def test_headless_show_env_flag_off_by_default_even_when_headed_true(monkeypatch):
    # "Quiet by default": HEADLESS_HEADED being the (default) True capability
    # flag must not make show True on its own.
    monkeypatch.setenv("HEADLESS_HEADED", "1")
    config = load_config()
    assert config.headed is True
    assert config.show is False


def test_config_is_frozen():
    config = load_config()
    with pytest.raises(Exception):
        config.headed = False
