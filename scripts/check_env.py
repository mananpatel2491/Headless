#!/usr/bin/env python3
"""check_env: environment self-test for Headless.

Background: the four things that failed or were missing while bootstrapping
this machine (D10): no `gcloud`, no CDP listener, Python 3.14 wheel doubt,
profile-directory policy. Run this after a fresh checkout, a Chrome update,
or an OS update, before trying a real errand.

Site: none. This maintenance script never opens a browser window and never
touches a site.
Reads: the Playwright browser cache, the profile directory, the vault.
Writes (up to): a probe file in the profile directory (removed immediately);
a `headless-selftest` vault item (removed immediately, keychain backend
only).
Secrets / profile fields: none beyond the vault self-test item.
Handoff: none; this is not a browser errand.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Same convention as the Director's Atlassian toolkit: no packaging step for a
# personal tool, just insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless.config import Config, ConfigError, load_config
from headless.secrets import open_vault

ROW_NAMES = ("browser", "playwright", "profile_dir", "vault")


def _check_browser() -> tuple[str, str]:
    """Chrome present: Playwright resolves and can briefly launch the 'chrome' channel."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            browser.close()
        return "PASS", ""
    except Exception as exc:
        return "FAIL", f"install Google Chrome, or confirm the 'chrome' channel resolves ({exc})"


def _check_playwright() -> tuple[str, str]:
    """Playwright runtime importable and its bundled Chromium cache present on disk."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            executable = Path(p.chromium.executable_path)
        if not executable.exists():
            return "FAIL", f"run 'python -m playwright install chromium' ({executable} missing)"
        return "PASS", ""
    except Exception as exc:
        return "FAIL", f"run 'pip install -r requirements.txt' ({exc})"


def _check_profile_dir(profile_dir: Path) -> tuple[str, str]:
    """Profile directory creatable and writable."""
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        probe_file = profile_dir / ".headless-check-env-probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        return "PASS", ""
    except OSError as exc:
        return "FAIL", f"check permissions on {profile_dir} ({exc})"


def _check_vault(config: Config) -> tuple[str, str]:
    """Vault reachable: keychain does put/get/delete of headless-selftest; gcp
    checks the client is constructible and the project is set."""
    try:
        vault = open_vault(config)
        if vault.self_test():
            return "PASS", ""
        return "FAIL", f"the {config.secrets_backend} backend self-test failed"
    except Exception as exc:
        return "FAIL", str(exc)


def _print_row(name: str, status: str, hint: str) -> None:
    line = f"{name:<12} {status}"
    if status != "PASS" and hint:
        line += f" - {hint}"
    print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Environment self-test for Headless (four PASS/FAIL/SKIP rows; opens no browser window)."
    )
    # No flags: check_env takes none. A minimal parser exists only so an
    # unrecognized flag (e.g. --submit) is refused (argparse exits 2) instead
    # of being silently ignored.
    parser.parse_args(argv)

    start = time.monotonic()

    try:
        config = load_config()
    except ConfigError as exc:
        # Config errors (e.g. HEADLESS_SECRETS_BACKEND=gcp without
        # HEADLESS_GCP_PROJECT) must fail before any other check runs and
        # before any browser launch (FR-004, SC-006: under 2 seconds).
        for name in ROW_NAMES[:-1]:
            _print_row(name, "SKIP", "skipped: configuration error, see vault row")
        _print_row("vault", "FAIL", str(exc))
        return 1

    rows = [
        ("browser", *_check_browser()),
        ("playwright", *_check_playwright()),
        ("profile_dir", *_check_profile_dir(config.profile_dir)),
        ("vault", *_check_vault(config)),
    ]
    for name, status, hint in rows:
        _print_row(name, status, hint)

    elapsed = time.monotonic() - start
    if elapsed > 25:
        print(f"(warning: check_env took {elapsed:.1f}s, budget is 30s)")

    return 0 if all(status == "PASS" for _, status, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
