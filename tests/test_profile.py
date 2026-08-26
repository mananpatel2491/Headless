"""Unit tests for headless/profile.py: loading the `profile` vault item as JSON,
dotted-path lookup, refusal of non-scalar results and missing paths, and a
clear error on malformed JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from headless.fields import FieldPlan
from headless.insurers import WALK_REGISTRY
from headless.profile import ProfileRegistry, RegistryAmbiguous, RegistryMissing


def test_load_and_get_scalar(fake_vault):
    fake_vault.put_secret(
        "profile",
        json.dumps({"identity": {"pan": "ABCDE1234F", "full_name": "Director"}}),
    )
    registry = ProfileRegistry.load(fake_vault)
    assert registry.get("identity.pan") == "ABCDE1234F"
    assert registry.get("identity.full_name") == "Director"


def test_load_uses_custom_item_name(fake_vault):
    fake_vault.put_secret("profile-alt", json.dumps({"a": {"b": "c"}}))
    registry = ProfileRegistry.load(fake_vault, item="profile-alt")
    assert registry.get("a.b") == "c"


def test_missing_path_raises_registry_missing(fake_vault):
    fake_vault.put_secret("profile", json.dumps({"identity": {"pan": "ABCDE1234F"}}))
    registry = ProfileRegistry.load(fake_vault)
    with pytest.raises(RegistryMissing) as exc_info:
        registry.get("identity.aadhaar")
    assert "identity.aadhaar" in str(exc_info.value)


def test_nested_dict_result_is_refused(fake_vault):
    fake_vault.put_secret("profile", json.dumps({"identity": {"pan": "ABCDE1234F"}}))
    registry = ProfileRegistry.load(fake_vault)
    with pytest.raises(RegistryMissing):
        registry.get("identity")


def test_malformed_json_raises_clear_error(fake_vault):
    fake_vault.put_secret("profile", "{not valid json")
    with pytest.raises(ValueError):
        ProfileRegistry.load(fake_vault)


# --- v0.0.5: type-discriminated array addressing (spec 005, T054) ----------
# research.md D13, spec FR-040 through FR-044, SC-016.

_ARRAY_DOC = {
    "identities": [
        {"type": "self", "first_name": "Test", "last_name": "Testerson"},
        {"type": "spouse", "first_name": "Spouse", "last_name": "Testerson"},
    ],
    "addresses": [
        {
            "type": "home",
            "line1": "1 Example Street",
            "zip": "48000",
            "nested": {"array": [{"type": "inner", "value": "found-it"}]},
        }
    ],
    "no_type_field": [{"first_name": "Nameless"}],
    "duplicate_type": [
        {"type": "dup", "value": "first"},
        {"type": "dup", "value": "second"},
    ],
}


@pytest.fixture
def array_vault(fake_vault):
    fake_vault.put_secret("profile", json.dumps(_ARRAY_DOC))
    return fake_vault


def test_array_element_selected_by_type_then_traversal_continues(array_vault):
    registry = ProfileRegistry.load(array_vault)
    assert registry.get("identities.self.first_name") == "Test"
    assert registry.get("identities.spouse.first_name") == "Spouse"
    assert registry.get("addresses.home.zip") == "48000"


def test_array_traversal_continues_through_a_nested_list(array_vault):
    registry = ProfileRegistry.load(array_vault)
    assert registry.get("addresses.home.nested.array.inner.value") == "found-it"


def test_zero_type_matches_raises_registry_missing_unchanged_shape(array_vault):
    registry = ProfileRegistry.load(array_vault)
    with pytest.raises(RegistryMissing) as exc_info:
        registry.get("identities.nonexistent.first_name")
    assert "identities.nonexistent.first_name" in str(exc_info.value)


def test_more_than_one_type_match_raises_registry_ambiguous_naming_only_the_path(array_vault):
    registry = ProfileRegistry.load(array_vault)
    with pytest.raises(RegistryAmbiguous) as exc_info:
        registry.get("duplicate_type.dup.value")
    message = str(exc_info.value)
    assert "duplicate_type.dup.value" in message
    # Value-free: neither matched element's own content ever appears.
    assert "first" not in message
    assert "second" not in message


def test_element_with_no_type_field_is_never_a_match_candidate(array_vault):
    registry = ProfileRegistry.load(array_vault)
    with pytest.raises(RegistryMissing):
        registry.get("no_type_field.anything.first_name")


def test_path_fully_consumed_on_a_list_or_dict_still_refuses(array_vault):
    registry = ProfileRegistry.load(array_vault)
    with pytest.raises(RegistryMissing):
        registry.get("identities")  # still a list
    with pytest.raises(RegistryMissing):
        registry.get("identities.self")  # still a dict (the matched element itself)


def test_existing_dict_and_scalar_behavior_is_unchanged_when_no_list_involved(fake_vault):
    fake_vault.put_secret("profile", json.dumps({"identity": {"pan": "ABCDE1234F"}}))
    registry = ProfileRegistry.load(fake_vault)
    assert registry.get("identity.pan") == "ABCDE1234F"
    with pytest.raises(RegistryMissing):
        registry.get("identity.missing")


# --- v0.0.5: profile.template.json drift test (spec FR-048, T058) ----------
# Loads the file directly - a plain file read, never through the vault,
# never prompting for a passphrase (NFR-002).

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "profile.template.json"


class _AnyPathRegistry:
    """A fake registry standing in for walk() construction only (FIX-FIRST
    2, Opus verifier, 2026-08-26): building a walk's Step list never
    actually resolves a registry: value - a FieldPlan's Source is stored
    unresolved and only read later, at fill/capture time, via
    fields.resolve_source(). This fake's own .get() is therefore never
    expected to be called by any current walk; it answers anyway (rather
    than raising) so a future walk that DOES inspect a registry value while
    building its own step list degrades to a dummy string instead of
    failing this drift test for an unrelated reason."""

    def get(self, dotted: str) -> str:
        return "dummy-value-not-actually-read-by-walk-construction"


def _registry_paths_referenced_by_shipped_walks() -> list[str]:
    """Derive every `registry:` path a shipped insurer walk references,
    mechanically - never a hand-maintained literal (FIX-FIRST 2, Opus
    verifier, 2026-08-26: a hand-maintained list can silently drift from
    the actual code the moment someone edits a walk and forgets to update
    it here too). Instantiates every `Errand` subclass registered in
    `headless.insurers.WALK_REGISTRY`, calls its own `walk(registry)`, and
    collects every `FieldPlan`'s `source.ref` where `source.kind ==
    "registry"`. A future walk change that adds a new registry-sourced
    `FieldPlan` is picked up here automatically, with no second place to
    remember to update - this is what makes FR-048's own "the test must
    fail if a walk outruns the template" guarantee actually mechanical,
    not just documented."""
    fake_registry = _AnyPathRegistry()
    paths: set[str] = set()
    for errand_cls in WALK_REGISTRY.values():
        errand = errand_cls()
        for step in errand.walk(fake_registry):
            if isinstance(step, FieldPlan) and step.source.kind == "registry":
                paths.add(step.source.ref)
    return sorted(paths)


# contracts/walk-capture-report.md section 8's own worked example
# (`vehicles.primary.currently_insured`) is kept as one explicit addition on
# top of the mechanically-derived set above, not derived from
# WALK_REGISTRY: no shipped walk in this delivery actually references it
# yet (implementation-time recon never reached the page FR-035 conditions
# its own wiring on - research.md's own "Recon results" section), but the
# contract discusses this exact path by name as a verified-resolving
# example of the array-addressing mechanism (FR-040 through FR-044), so
# this drift test keeps proving it resolves too, independent of whether any
# walk references it.
_SHIPPED_WALK_PATHS = sorted(
    set(_registry_paths_referenced_by_shipped_walks()) | {"vehicles.primary.currently_insured"}
)


def test_mechanical_derivation_actually_found_the_progressive_walks_own_path():
    # Sanity check on the derivation mechanism itself (FIX-FIRST 2): proves
    # _registry_paths_referenced_by_shipped_walks() is not silently
    # returning an empty set - it genuinely walked ProgressiveQuoteErrand
    # and found its one registry-sourced FieldPlan.
    assert "addresses.home.zip" in _registry_paths_referenced_by_shipped_walks()


def test_derivation_mechanism_would_fail_a_walk_referencing_an_undefined_path():
    # Proves the mechanism is genuinely mechanical, not merely correct by
    # coincidence for the one path this delivery ships: a fixture walk
    # referencing a path the template does not define must make the same
    # resolve-against-template step this file's own drift tests use fail,
    # without needing a change to _registry_paths_referenced_by_shipped_walks
    # itself - only its input (which walks exist) changes.
    from headless.errand import Errand
    from headless.fields import parse_source

    class _FixtureErrandWithAnUndefinedPath(Errand):
        name = "fixture-undefined-path"
        HANDOFF = "n/a"
        dependencies: list[str] = []

        def walk(self, registry):
            return [
                FieldPlan(
                    name="Bad",
                    selector="#bad",
                    source=parse_source("registry:addresses.home.some_field_no_template_defines"),
                )
            ]

    fake_registry = _AnyPathRegistry()
    fixture_paths = {
        step.source.ref
        for step in _FixtureErrandWithAnUndefinedPath().walk(fake_registry)
        if isinstance(step, FieldPlan) and step.source.kind == "registry"
    }
    assert fixture_paths == {"addresses.home.some_field_no_template_defines"}

    document = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    registry = ProfileRegistry(document)
    with pytest.raises(RegistryMissing):
        for path in fixture_paths:
            registry.get(path)


def test_profile_template_json_exists_at_repository_root():
    assert _TEMPLATE_PATH.exists(), (
        "profile.template.json must exist at the repository root (research.md D14); "
        "this delivery must never create or recreate it as a second file (FR-049)"
    )


def test_drift_every_shipped_walk_path_resolves_against_the_real_template():
    document = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    registry = ProfileRegistry(document)
    for path in _SHIPPED_WALK_PATHS:
        # Any failure here (RegistryMissing/RegistryAmbiguous) fails this
        # test - the drift guard FR-048 describes.
        value = registry.get(path)
        assert isinstance(value, str)


def test_drift_logic_against_a_synthetic_in_memory_fixture_standing_in_for_the_template():
    # SC-018: the same drift-checking logic, proven correct against a
    # synthetic fixture document shaped like the template - a direct
    # drop-in equivalent of the real-template test above, independent of
    # whether the real file happens to be present.
    fixture_document = {
        "identities": [{"type": "self", "first_name": "Test"}],
        "addresses": [{"type": "home", "line1": "1 Example Street", "zip": "48000"}],
        "vehicles": [{"type": "primary", "vin": "1SAMPLE0VIN000001", "currently_insured": "yes"}],
        "feature_configs": {"insurance": {"companies": ["progressive"]}},
    }
    registry = ProfileRegistry(fixture_document)
    for path in _SHIPPED_WALK_PATHS:
        value = registry.get(path)
        assert isinstance(value, str)


def test_drift_a_path_the_template_does_not_define_fails_resolution():
    document = json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    registry = ProfileRegistry(document)
    with pytest.raises(RegistryMissing):
        registry.get("addresses.home.some_field_no_walk_ships_and_the_template_lacks")
