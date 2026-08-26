#!/usr/bin/env python3
"""policy_extract: turn an insured asset's policy_doc PDF into a confirmed
current-policy reference (spec 005-insurance-quote-comparison, User Story 3,
research.md D15, contracts/walk-capture-report.md section 9).

Background: `current_policy` is not hand-typed into the `profile` vault
item; each insured asset (an `addresses[]`/`vehicles[]` element) carries its
own `policy_doc` field, a filesystem path to the PDF of the policy currently
covering it. This script extracts a best-effort candidate from that PDF via
`headless/policydoc.py` (`pypdf`, deterministic heuristics only, no LLM call
anywhere), prints it to the Director's own terminal for review, and caches
only a confirmed (accepted-or-corrected) result under
`reports/policy/<asset-key>.json`.

Site: none. This maintenance-adjacent script never opens a browser window
(the same category `scripts/vault.py` and `scripts/scan_secrets.py`
occupy).
Reads: the `profile` vault item's `addresses`/`vehicles` arrays (one
passphrase prompt for the whole run); the PDF file named by each eligible
element's `policy_doc`.
Writes: `reports/policy/<asset-key>.json`, mode `0600` where the platform
supports it - only for an asset whose extraction candidate the Director
explicitly confirmed (accepted or corrected).
Secrets / profile fields: `profile`'s `addresses`/`vehicles` arrays, read by
a direct JSON parse - never through `ProfileRegistry`, which was built for
single-element `type`-addressing, not enumeration (research.md D3).
Handoff: none; this is not a browser errand.

Usage:
    python scripts/policy_extract.py                    # every eligible asset
    python scripts/policy_extract.py vehicles.primary    # one asset only

Exit codes: 0 on completion (regardless of how many assets were skipped,
declined, or extracted with zero lines - none of those are failures); 1 a
vault-level refusal (missing vault file, wrong passphrase, malformed
`profile` JSON); 2 a usage error (a malformed asset-path argument, or
argparse's own handling).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Same convention as the Director's Atlassian toolkit: no packaging step for a
# personal tool, just insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless.capture import reports_dir_for
from headless.config import ConfigError, load_config
from headless.gates import GateRefused
from headless.policydoc import (
    PolicyReference,
    confirm_candidate,
    derive_asset_key,
    extract_candidate,
    is_excluded,
    write_policy_reference,
)
from headless.profile import ProfileError
from headless.secrets import SecretMissing, open_vault

_ARRAYS = ("addresses", "vehicles")

# The vault item name every ProfileError message below names, matching
# ProfileRegistry.load's own default `item="profile"` parameter exactly
# (NIT 7, Opus verifier, 2026-08-26).
PROFILE_ITEM = "profile"


def _eligible_assets(profile_doc: dict, only_path: str | None) -> list[tuple[str, dict]]:
    """Yields `(array_name, element)` pairs for every element that has a
    real (non-`"n/a"`) `policy_doc` set and is not excluded (FR-050,
    FR-058, FR-062). `only_path` (e.g. `"vehicles.primary"`) restricts to
    one element. Raises `ValueError` on a malformed `only_path` - the
    caller turns that into a usage-error exit."""
    only_array = only_type = None
    if only_path:
        parts = only_path.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"asset path {only_path!r} must be '<array>.<type>' (e.g. vehicles.primary)")
        only_array, only_type = parts

    result: list[tuple[str, dict]] = []
    for array_name in _ARRAYS:
        if only_array is not None and array_name != only_array:
            continue
        for element in profile_doc.get(array_name, []):
            if not isinstance(element, dict):
                continue
            if only_type is not None and element.get("type") != only_type:
                continue
            if is_excluded(element):
                continue
            policy_doc = element.get("policy_doc")
            if not policy_doc or policy_doc == "n/a":
                continue
            result.append((array_name, element))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract, confirm, and cache a current-policy reference from a policy PDF."
    )
    parser.add_argument(
        "asset",
        nargs="?",
        default=None,
        help="Restrict to one asset, e.g. vehicles.primary. Default: every eligible asset.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config()
        vault = open_vault(config)
        raw_profile = vault.get_secret("profile")
    except (ConfigError, GateRefused, SecretMissing) as exc:
        print(f"REFUSED: {exc}")
        return 1

    # NIT 7 (Opus verifier, 2026-08-26): a malformed profile document is
    # profile's own existing ProfileError (spec 001), not a new class this
    # feature adds - construct and raise the real class, in the same
    # message shape ProfileRegistry.load's own internal parse already
    # uses, rather than a divergent ad-hoc string.
    try:
        profile_doc = json.loads(raw_profile)
    except json.JSONDecodeError as exc:
        print(f"REFUSED: {ProfileError(f'vault item {PROFILE_ITEM!r} is not valid JSON: {exc}')}")
        return 1
    if not isinstance(profile_doc, dict):
        print(f"REFUSED: {ProfileError(f'vault item {PROFILE_ITEM!r} must be a JSON object')}")
        return 1

    try:
        assets = _eligible_assets(profile_doc, args.asset)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2

    if not assets:
        print("no eligible assets (none has a real policy_doc, or all are excluded/out of scope)")
        return 0

    reports_dir = reports_dir_for(config)
    for array_name, element in assets:
        asset_key = derive_asset_key(array_name, element.get("type", ""))
        pdf_path = Path(element["policy_doc"])
        print(f"--- {asset_key} ({pdf_path}) ---")
        candidate = extract_candidate(pdf_path)
        if candidate is None:
            print(f"note: no candidate extracted for {asset_key} (unreadable PDF or zero coverage lines parsed)")
            continue
        confirmed = confirm_candidate(candidate)
        if confirmed is None:
            print(f"note: {asset_key} not confirmed; nothing cached")
            continue
        reference = PolicyReference(
            policy=confirmed,
            asset_key=asset_key,
            source_path=str(pdf_path),
            confirmed_at=datetime.now(timezone.utc).isoformat(),
        )
        path = write_policy_reference(reference, reports_dir)
        print(f"cached: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
