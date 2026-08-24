"""Unit tests for headless/profile.py: loading the `profile` vault item as JSON,
dotted-path lookup, refusal of non-scalar results and missing paths, and a
clear error on malformed JSON.
"""

from __future__ import annotations

import json

import pytest

from headless.profile import ProfileRegistry, RegistryMissing


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
