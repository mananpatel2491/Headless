#!/usr/bin/env python3
"""policy_extract: turn an insured asset's policy_doc PDF into a confirmed
current-policy reference (spec 005-insurance-quote-comparison, User Story 3,
research.md D15, contracts/walk-capture-report.md section 9; extraction
pipeline replaced by spec 006-policy-extraction-v2).

Background: `current_policy` is not hand-typed into the `profile` vault
item; each insured asset (an `addresses[]`/`vehicles[]` element) carries its
own `policy_doc` field, a filesystem path to the PDF of the policy currently
covering it. This script converts that PDF with layout awareness, proposes a
candidate via a local-only Ollama model (falling back automatically to the
v0.0.5 regex-based heuristics whenever the local model is unavailable,
unreachable, or `--no-llm` was passed), runs a mechanical sanity pass that
strips any figure absent from the converted source text
(`headless/policydoc.py`'s `extract_candidate_v2`), prints the result to the
Director's own terminal for review, and caches only a confirmed
(accepted-or-corrected) result under `reports/policy/<asset-key>.json`. No
call of any kind ever reaches a non-local endpoint (`headless/config.py`'s
own localhost-only `ConfigError`).

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
    python scripts/policy_extract.py --no-llm            # regex heuristics only,
                                                          # never attempts a local model

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
    extract_candidate_v2,
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
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip the local-model attempt entirely; every candidate comes from the "
        "regex-based generator (spec 006-policy-extraction-v2, FR-014).",
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
    use_llm = not args.no_llm
    for array_name, element in assets:
        asset_key = derive_asset_key(array_name, element.get("type", ""))
        pdf_path = Path(element["policy_doc"])
        print(f"--- {asset_key} ({pdf_path}) ---")
        result = extract_candidate_v2(pdf_path, config=config, use_llm=use_llm)
        if result is None:
            print(f"note: no candidate extracted for {asset_key} (unreadable PDF or zero coverage lines parsed)")
            continue
        candidate, generator_name, converter_name = result
        # Value-free (a package name, never document content): which
        # converter served this run (spec 006 FR-001/FR-002, quickstart.md
        # Scenario 1 step 1).
        print(f"note: converted via {converter_name}")
        confirmed = confirm_candidate(candidate)
        if confirmed is None:
            print(f"note: {asset_key} not confirmed; nothing cached")
            continue
        reference = PolicyReference(
            policy=confirmed,
            asset_key=asset_key,
            source_path=str(pdf_path),
            confirmed_at=datetime.now(timezone.utc).isoformat(),
            generator=generator_name,
            converter=converter_name,
            # spec 007-extraction-fidelity, FR-017: the sanity pass's own
            # warnings, carried through to the cached reference - `candidate`
            # (the pre-confirmation ExtractionCandidate) is unmutated by
            # confirm_candidate, so its own `warnings` list is still exactly
            # what the Director reviewed at the prompt above.
            #
            # MINOR 8 (Opus verifier, 2026-08-30) - semantics, not a
            # behavior change: this is always "warnings AT THE MOMENT OF
            # REVIEW," never a live description of the cached policy's own
            # current state. If the Director chose "correct" and pasted a
            # hand-typed replacement document, `confirmed` may address (or
            # be unrelated to) exactly what a given warning named - this
            # field still records what the sanity pass found BEFORE that
            # correction, the same audit-trail role `source_path`/
            # `confirmed_at` already play (a fact about the extraction
            # attempt, not an assertion about the final cached value).
            warnings=list(candidate.warnings),
        )
        path = write_policy_reference(reference, reports_dir)
        print(f"cached: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
