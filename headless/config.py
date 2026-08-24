"""Non-secret configuration for Headless.

Loaded from `.env` (repo root, via python-dotenv) then the environment, with
command-line overrides on top. Validation happens here, before any browser or
vault call (FR-004, SC-006): an invalid or incomplete configuration raises
ConfigError immediately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VALID_SECRETS_BACKENDS = ("keychain", "gcp")


class ConfigError(RuntimeError):
    """Configuration is invalid or incomplete; raised before any browser or vault call."""


@dataclass(frozen=True)
class Config:
    profile_dir: Path
    headed: bool
    cdp_url: str | None
    secrets_backend: str
    keychain_account: str
    gcp_project: str | None
    preview_dir: Path
    screenshots: bool = True
    show: bool = False


def _repo_root() -> Path:
    # headless/config.py -> headless/ -> repo root
    return Path(__file__).resolve().parent.parent


def _env_flag(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def load_config(overrides: dict[str, object] | None = None) -> Config:
    """Build a Config from `.env`, the environment, and CLI overrides (CLI wins).

    `overrides` carries only the keys an errand's argparse actually set; absent
    keys fall back to the environment, then the documented default.
    """
    overrides = dict(overrides or {})
    repo_root = _repo_root()

    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    def pick(key: str, env_name: str, default: str = "") -> str:
        value = overrides.get(key)
        if value:
            return str(value)
        return os.environ.get(env_name, default)

    profile_dir = Path(pick("profile_dir", "HEADLESS_PROFILE_DIR", "~/.headless/chrome-profile")).expanduser()

    if overrides.get("headless"):
        headed = False
    else:
        headed = _env_flag(os.environ.get("HEADLESS_HEADED"), True)

    cdp_url = pick("cdp_url", "HEADLESS_CDP_URL", "") or None

    secrets_backend = pick("secrets_backend", "HEADLESS_SECRETS_BACKEND", "keychain")
    if secrets_backend not in VALID_SECRETS_BACKENDS:
        raise ConfigError(
            f"HEADLESS_SECRETS_BACKEND={secrets_backend!r} must be one of {list(VALID_SECRETS_BACKENDS)}"
        )

    keychain_account = pick("keychain_account", "HEADLESS_KEYCHAIN_ACCOUNT", "headless")

    gcp_project = pick("gcp_project", "HEADLESS_GCP_PROJECT", "") or None
    if secrets_backend == "gcp" and not gcp_project:
        raise ConfigError("HEADLESS_SECRETS_BACKEND=gcp requires HEADLESS_GCP_PROJECT to be set")

    # The default resolves against the repo root, never the process's cwd
    # (FIX-FIRST 6): otherwise `probe.py` run from another directory would
    # silently write previews under that directory instead of the repo's
    # previews/. Any OTHER relative value is rejected outright (N3): a
    # relative override could otherwise land anywhere, including outside the
    # gitignored previews/ tree, so only an absolute path or the literal
    # default string is accepted.
    preview_dir_raw = pick("preview_dir", "HEADLESS_PREVIEW_DIR", "previews")
    preview_dir = Path(preview_dir_raw).expanduser()
    if not preview_dir.is_absolute():
        if preview_dir_raw != "previews":
            raise ConfigError(
                "HEADLESS_PREVIEW_DIR (or --preview-dir) must be absolute or the default 'previews' "
                "(relative paths would escape .gitignore)"
            )
        preview_dir = repo_root / preview_dir

    if "screenshots" in overrides:
        screenshots = bool(overrides["screenshots"])
    else:
        screenshots = _env_flag(os.environ.get("HEADLESS_SCREENSHOTS"), True)

    # "Quiet by default" (v0.0.1, Director decision 2026-08-24): `show` is the
    # second, independent axis from `headed`. `headed` still means "the
    # environment can produce a real windowed Chrome process at all" (gates
    # apply). `show` means "make the window visible from launch" and defaults
    # to False regardless of HEADLESS_HEADED - see session.py for how the two
    # combine per mode.
    if overrides.get("show"):
        show = True
    else:
        show = _env_flag(os.environ.get("HEADLESS_SHOW"), False)

    return Config(
        profile_dir=profile_dir,
        headed=headed,
        cdp_url=cdp_url,
        secrets_backend=secrets_backend,
        keychain_account=keychain_account,
        gcp_project=gcp_project,
        preview_dir=preview_dir,
        screenshots=screenshots,
        show=show,
    )
