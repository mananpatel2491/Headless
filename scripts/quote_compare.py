#!/usr/bin/env python3
"""quote_compare: the multi-insurer orchestrator (spec 005-insurance-quote-comparison,
User Story 4, contracts/walk-capture-report.md section 4).

Background: the Director's own `profile` document names which insurers he
wants compared (`feature_configs.insurance.companies`); this script composes
each mapped insurer's own `Errand` subclass (`headless.insurers.
WALK_REGISTRY`) rather than reimplementing session/gate/vault machinery a
second time - an insurer with no registered walk becomes a "not mapped yet"
report row, and one insurer's own walk failure never stops the rest
(research.md D7). Not an `Errand` subclass itself: it composes several, and
`Errand.url()`/`dependencies` are single-site concepts by design.

Site: none directly - every browser action happens inside a mapped
insurer's own `Errand.run()` call, reused unmodified.
Reads: `profile`'s `feature_configs.insurance.companies` (a direct JSON
parse, never through `ProfileRegistry` - it ends on a list, research.md
D3); the confirmed current-policy reference from
`reports/policy/vehicles-primary.json`, when one exists (never a refusal
when it is absent or unparseable, FR-046/FR-058); each mapped insurer's own
freshest capture file.
Writes (up to): nothing on any site directly; in apply mode, one HTML
report at `reports/quote-comparison-<date>.html`.
Secrets / profile fields: `feature_configs.insurance.companies`; every
mapped insurer's own registry-sourced fields, resolved inside its own
`Errand.run()` call.
Handoff: none of its own; each mapped insurer's own `Errand.run()` call
handles its own `HumanStep`/trailing handoff internally.

Usage:
    python scripts/quote_compare.py [--apply|--check] [--profile-dir PATH]
        [--headless|--show] [--preview-dir PATH] [--no-screenshot]

Exit codes: 0 when preview/check completed, or a report was written in
apply mode (including the excluded-asset report) - regardless of how many
individual insurers failed and regardless of whether a confirmed
current-policy reference existed (spec FR-030, NFR-004); 1 when `profile`
itself was invalid JSON, or `feature_configs.insurance.companies` was
missing or malformed; 2 for a usage error (argparse's own handling of the
standard mode flags).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Same convention as the Director's Atlassian toolkit: no packaging step for a
# personal tool, just insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless import compare, policydoc, report
from headless.capture import QuoteInputError, parse_companies, read_freshest_capture, reports_dir_for
from headless.config import ConfigError, load_config
from headless.gates import GateRefused, add_mode_arguments
from headless.insurers import WALK_REGISTRY
from headless.profile import ProfileError
from headless.secrets import SecretMissing, open_vault

# This delivery's own comparison targets exactly one asset (spec FR-060): a
# future homeowners-/renters-insurance spec would target a different asset
# key via its own orchestrator; this script must not read or write any
# other asset key's cache file.
_TARGET_ARRAY = "vehicles"
_TARGET_TYPE = "primary"
_TARGET_ASSET_KEY = "vehicles-primary"
_TARGET_ASSET_PATH = "vehicles.primary"

# The vault item name every ProfileError message below names, matching
# ProfileRegistry.load's own default `item="profile"` parameter exactly
# (NIT 7, Opus verifier, 2026-08-26).
PROFILE_ITEM = "profile"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare insurance quotes across every mapped insurer in "
        "feature_configs.insurance.companies."
    )
    add_mode_arguments(parser)
    return parser


def _config_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Mirrors `Errand._overrides(args)` exactly (`headless/errand.py`) so
    this orchestrator's own `load_config()` call honors the same CLI flags
    every errand already does - not only forwarding them to each mapped
    insurer's own `Errand.run()` call, but also using them for this
    script's own `reports_dir_for(config)` resolution."""
    overrides: dict[str, object] = {}
    if getattr(args, "profile_dir", None):
        overrides["profile_dir"] = args.profile_dir
    if getattr(args, "headless", False):
        overrides["headless"] = True
    if getattr(args, "preview_dir", None):
        overrides["preview_dir"] = args.preview_dir
    if getattr(args, "no_screenshot", False):
        overrides["screenshots"] = False
    if getattr(args, "show", False):
        overrides["show"] = True
    return overrides


def _forward_argv(args: argparse.Namespace) -> list[str]:
    """Reconstructs an argv list from this orchestrator's own parsed flags,
    forwarded unchanged to each mapped insurer's own `Errand.run()` call
    (spec FR-026, contracts section 4's own flag-forwarding table)."""
    forwarded: list[str] = []
    if args.apply:
        forwarded.append("--apply")
    if args.check:
        forwarded.append("--check")
    if args.profile_dir:
        forwarded += ["--profile-dir", args.profile_dir]
    if args.headless:
        forwarded.append("--headless")
    if args.show:
        forwarded.append("--show")
    if args.preview_dir:
        forwarded += ["--preview-dir", args.preview_dir]
    if args.no_screenshot:
        forwarded.append("--no-screenshot")
    return forwarded


def _find_target_asset(profile_doc: dict) -> dict | None:
    for element in profile_doc.get(_TARGET_ARRAY, []):
        if isinstance(element, dict) and element.get("type") == _TARGET_TYPE:
            return element
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    forwarded = _forward_argv(args)
    mode_name = "apply" if args.apply else ("check" if args.check else "preview")

    # Startup sequence, steps 1-4 (contracts section 4): profile itself must
    # parse before anything downstream is trusted.
    try:
        config = load_config(_config_overrides(args))
        vault = open_vault(config)
        raw_profile = vault.get_secret("profile")
    except (ConfigError, GateRefused, SecretMissing) as exc:
        print(f"REFUSED: {exc}")
        return 1

    # NIT 7 (Opus verifier, 2026-08-26): a malformed profile document is
    # profile's own existing ProfileError (spec 001), not a new class this
    # feature adds (contracts section 4 step 3) - construct and raise the
    # real class, in the same message shape ProfileRegistry.load's own
    # internal parse already uses, rather than a divergent ad-hoc string.
    try:
        profile_doc = json.loads(raw_profile)
    except json.JSONDecodeError as exc:
        print(f"REFUSED: {ProfileError(f'vault item {PROFILE_ITEM!r} is not valid JSON: {exc}')}")
        return 1
    if not isinstance(profile_doc, dict):
        print(f"REFUSED: {ProfileError(f'vault item {PROFILE_ITEM!r} must be a JSON object')}")
        return 1

    try:
        companies_fragment = profile_doc.get("feature_configs", {}).get("insurance", {}).get("companies")
        companies = parse_companies(companies_fragment)
    except QuoteInputError as exc:
        print(f"REFUSED: {exc}")
        return 1

    reports_dir = reports_dir_for(config)

    # Step 5: the "n/a" exclusion sentinel check - before any insurer's
    # Errand is constructed, in every mode (spec FR-060, FR-063, FR-064).
    target_asset = _find_target_asset(profile_doc)
    excluded = policydoc.is_excluded(target_asset) if target_asset is not None else False
    if excluded:
        print(f"{_TARGET_ASSET_PATH} excluded by profile (n/a) - no insurer journeys run")
        if mode_name == "apply":
            html = report.render_exclusion_report(_TARGET_ASSET_PATH)
            path = report.write_report(html, reports_dir)
            print(f"REPORT {path}")
        return 0

    # Step 6: partition.
    mapped = [c for c in companies if c in WALK_REGISTRY]
    unmapped = [c for c in companies if c not in WALK_REGISTRY]
    for insurer in unmapped:
        print(f"not mapped yet: {insurer}")

    # Step 7: dispatch.
    if mode_name in ("preview", "check"):
        for insurer in mapped:
            errand_cls = WALK_REGISTRY[insurer]
            print(f"=== {insurer} ===")
            errand_cls().run(forwarded)
        return 0

    # Apply mode: run every mapped insurer in sequence, recording exit
    # codes value-free (spec FR-029); one failure never stops the rest
    # (NFR-004) or the report step that follows.
    for insurer in mapped:
        errand_cls = WALK_REGISTRY[insurer]
        print(f"=== {insurer} ===")
        exit_code = errand_cls().run(forwarded)
        if exit_code != 0:
            print(f"note: {insurer} walk failed (exit {exit_code})")

    # An insurer counts as failed for the report's own purposes only when it
    # has never produced ANY capture, ever - not merely when this run's own
    # attempt returned non-zero (research.md D7/FR-021's "freshest capture
    # regardless of which run produced it" rule).
    freshest = {insurer: read_freshest_capture(insurer, reports_dir) for insurer in mapped}
    failed = [insurer for insurer, cap in freshest.items() if cap is None]
    captures = {insurer: cap for insurer, cap in freshest.items() if cap is not None}

    current_policy = policydoc.read_policy_reference(_TARGET_ASSET_KEY, reports_dir)
    provenance = policydoc.read_policy_reference_provenance(_TARGET_ASSET_KEY, reports_dir)
    if provenance:
        # spec 007-extraction-fidelity, FR-017/FR-018: the tuple gained a
        # 5th element, warnings - not surfaced in the rendered report
        # (spec.md's own Out of Scope: no report.py rendering change beyond
        # what keeping the provenance footer consistent strictly requires),
        # so it is unpacked here and simply left unused.
        (
            current_policy_source,
            current_policy_confirmed_at,
            current_policy_generator,
            current_policy_converter,
            _current_policy_warnings,
        ) = provenance
    else:
        current_policy_source = current_policy_confirmed_at = None
        current_policy_generator = current_policy_converter = None

    comparison = compare.build_comparison(current_policy, captures)
    html = report.render_report(
        comparison,
        unmapped,
        failed,
        current_policy=current_policy,
        current_policy_source=current_policy_source,
        current_policy_confirmed_at=current_policy_confirmed_at,
        current_policy_generator=current_policy_generator,
        current_policy_converter=current_policy_converter,
    )
    path = report.write_report(html, reports_dir)
    print(f"REPORT {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
