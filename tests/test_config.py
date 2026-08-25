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
    "HEADLESS_AGE_FILE",
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
    # spec 004-age-vault, FR-002: "age" is the default (was "keychain").
    assert config.secrets_backend == "age"
    assert config.keychain_account == "headless"
    assert config.gcp_project is None
    assert config.age_file == Path("~/.headless/profile.age").expanduser()
    # FIX-FIRST 6: the default resolves against the repo root, not cwd.
    assert config.preview_dir == REPO_ROOT / "previews"
    assert config.screenshots is True
    assert config.show is False


# --- T010, T011 (spec 004-age-vault): default backend + age_file resolution


def test_default_secrets_backend_is_age(monkeypatch):
    # SC-003: load_config() with HEADLESS_SECRETS_BACKEND unset (and no
    # override) resolves secrets_backend == "age".
    config = load_config()
    assert config.secrets_backend == "age"


def test_age_file_default_is_tilde_expanded():
    config = load_config()
    assert config.age_file == Path.home() / ".headless" / "profile.age"
    assert "~" not in str(config.age_file)


def test_age_file_absolute_override_is_used_as_is():
    config = load_config(overrides={"age_file": "/tmp/headless-vault-test.age"})
    assert config.age_file == Path("/tmp/headless-vault-test.age")


def test_age_file_absolute_env_override_is_used_as_is(monkeypatch, tmp_path):
    monkeypatch.setenv("HEADLESS_AGE_FILE", str(tmp_path / "vault.age"))
    config = load_config()
    assert config.age_file == tmp_path / "vault.age"


def test_age_file_relative_override_raises(monkeypatch):
    # research.md D2: mirrors HEADLESS_PREVIEW_DIR's own relative-path
    # refusal, but with no literal-default carve-out (the default itself
    # always expands absolute).
    with pytest.raises(ConfigError) as exc_info:
        load_config(overrides={"age_file": "myvault.age"})
    assert "HEADLESS_AGE_FILE" in str(exc_info.value)


def test_age_file_relative_env_override_raises(monkeypatch):
    monkeypatch.setenv("HEADLESS_AGE_FILE", "myvault.age")
    with pytest.raises(ConfigError) as exc_info:
        load_config()
    assert "HEADLESS_AGE_FILE" in str(exc_info.value)


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
