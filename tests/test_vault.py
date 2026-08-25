"""Unit tests for scripts/vault.py: init/set/unset/list/path, each against an
injectable fake runner - zero real `age` invocations and zero passphrase
prompts (NFR-002, spec 004-age-vault). The fake runner dispatches on argv
shape (`age -d ...` vs `age -e -p -a`) the same way
headless/secrets.py's AgeBackend tests do.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import scripts.vault as vault

DISTINCTIVE_VALUE = "fixture-distinctive-value-should-never-print-Q7z"


class _FakeRunner:
    """Records every argv and every piped `input=` payload it was called
    with, and returns a canned age -d / age -e result depending on which
    subcommand (`-d` decrypt or `-e` encrypt) the argv names. Never touches
    the real `age` binary."""

    def __init__(
        self,
        decrypt_document: dict[str, str] | None = None,
        decrypt_returncode: int = 0,
        encrypt_returncode: int = 0,
        encrypt_stdout: bytes = b"fixture-ciphertext",
    ) -> None:
        self.calls: list[list[str]] = []
        self.stdin_payloads: list[bytes] = []
        self._decrypt_document = {} if decrypt_document is None else decrypt_document
        self._decrypt_returncode = decrypt_returncode
        self._encrypt_returncode = encrypt_returncode
        self._encrypt_stdout = encrypt_stdout

    def __call__(self, argv: list[str], **kwargs):
        self.calls.append(argv)
        if "input" in kwargs:
            self.stdin_payloads.append(kwargs["input"])
        if argv[:2] == ["age", "-d"]:
            return SimpleNamespace(
                returncode=self._decrypt_returncode,
                stdout=json.dumps(self._decrypt_document).encode("utf-8"),
                stderr=b"",
            )
        if argv[:2] == ["age", "-e"]:
            return SimpleNamespace(returncode=self._encrypt_returncode, stdout=self._encrypt_stdout, stderr=b"")
        raise AssertionError(f"unexpected argv: {argv}")


@pytest.fixture(autouse=True)
def age_file_env(monkeypatch, tmp_path):
    """Every test gets its own tmp_path vault file, resolved via
    HEADLESS_AGE_FILE the same way a real invocation would (vault.py has no
    --age-file CLI flag, per contracts/vault-and-cli.md)."""
    monkeypatch.delenv("HEADLESS_SECRETS_BACKEND", raising=False)
    vault_file = tmp_path / "vault.age"
    monkeypatch.setenv("HEADLESS_AGE_FILE", str(vault_file))
    return vault_file


# --- T019: init ----------------------------------------------------------


def test_init_creates_vault_when_absent(age_file_env, capsys):
    vault_file = age_file_env
    runner = _FakeRunner()

    exit_code = vault.main(["init"], runner=runner)

    assert exit_code == 0
    assert runner.calls == [["age", "-e", "-p", "-a"]]
    assert json.loads(runner.stdin_payloads[0].decode("utf-8")) == {}
    assert vault_file.exists()
    assert vault_file.read_bytes() == b"fixture-ciphertext"
    out = capsys.readouterr().out
    assert str(vault_file) in out


def test_init_refuses_when_vault_file_already_present(age_file_env, capsys):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner()

    exit_code = vault.main(["init"], runner=runner)

    assert exit_code == 1
    assert runner.calls == []  # refused before any age invocation
    assert vault_file.read_text(encoding="utf-8") == "existing-ciphertext"
    out = capsys.readouterr().out
    assert "REFUSED" in out


# --- T020: set / unset -----------------------------------------------------


def test_set_stores_value_via_getpass_never_argv(age_file_env, monkeypatch):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_document={"existing": "keepme"})
    monkeypatch.setattr(vault.getpass, "getpass", lambda prompt="": DISTINCTIVE_VALUE)

    exit_code = vault.main(["set", "profile"], runner=runner)

    assert exit_code == 0
    assert [call[:2] for call in runner.calls] == [["age", "-d"], ["age", "-e"]]
    written = json.loads(runner.stdin_payloads[0].decode("utf-8"))
    assert written == {"existing": "keepme", "profile": DISTINCTIVE_VALUE}
    # SC-008: the value never appears on any captured subprocess argv.
    for call in runner.calls:
        assert DISTINCTIVE_VALUE not in call


def test_unset_removes_existing_key(age_file_env):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_document={"profile": "keep", "gone": "bye"})

    exit_code = vault.main(["unset", "gone"], runner=runner)

    assert exit_code == 0
    written = json.loads(runner.stdin_payloads[0].decode("utf-8"))
    assert written == {"profile": "keep"}


def test_unset_absent_name_still_succeeds(age_file_env):
    # FR-018: idempotent, unchanged exit code whether or not NAME was present.
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_document={"profile": "keep"})

    exit_code = vault.main(["unset", "never-there"], runner=runner)

    assert exit_code == 0
    written = json.loads(runner.stdin_payloads[0].decode("utf-8"))
    assert written == {"profile": "keep"}


def test_set_failed_decrypt_never_reaches_reencrypt(age_file_env, monkeypatch):
    # data-model.md's failure isolation: a failed DECRYPT never reaches
    # MUTATE or RE-ENCRYPT.
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_returncode=1)
    monkeypatch.setattr(vault.getpass, "getpass", lambda prompt="": "value-should-never-be-used")

    exit_code = vault.main(["set", "profile"], runner=runner)

    assert exit_code == 1
    assert runner.calls == [["age", "-d", str(vault_file)]]  # re-encrypt never attempted


def test_unset_failed_decrypt_never_reaches_reencrypt(age_file_env):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_returncode=1)

    exit_code = vault.main(["unset", "profile"], runner=runner)

    assert exit_code == 1
    assert runner.calls == [["age", "-d", str(vault_file)]]


def test_set_missing_vault_file_refuses_with_zero_runner_calls(age_file_env):
    runner = _FakeRunner()
    exit_code = vault.main(["set", "profile"], runner=runner)
    assert exit_code == 1
    assert runner.calls == []


def test_unset_missing_vault_file_refuses_with_zero_runner_calls(age_file_env):
    runner = _FakeRunner()
    exit_code = vault.main(["unset", "profile"], runner=runner)
    assert exit_code == 1
    assert runner.calls == []


# --- T021: list / path ------------------------------------------------------


def test_list_prints_names_only_sorted(age_file_env, capsys):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_document={"zeta": DISTINCTIVE_VALUE, "alpha": "another-fixture-value-9k"})

    exit_code = vault.main(["list"], runner=runner)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.splitlines() == ["alpha", "zeta"]
    assert DISTINCTIVE_VALUE not in out
    assert "another-fixture-value-9k" not in out


def test_list_empty_vault_prints_zero_lines(age_file_env, capsys):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    runner = _FakeRunner(decrypt_document={})

    exit_code = vault.main(["list"], runner=runner)

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_list_missing_vault_file_refuses(age_file_env):
    runner = _FakeRunner()
    exit_code = vault.main(["list"], runner=runner)
    assert exit_code == 1
    assert runner.calls == []


def test_path_prints_resolved_path_and_never_calls_runner(age_file_env, capsys):
    vault_file = age_file_env
    calls: list[list[str]] = []

    def fail_runner(argv, **kwargs):
        calls.append(argv)
        raise AssertionError("path must never invoke the runner, decrypt or encrypt")

    exit_code = vault.main(["path"], runner=fail_runner)

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out == str(vault_file)
    assert calls == []


# --- FIX-FIRST 2 (v0.0.4 verifier pass): atomic-write cleanup + mode 0600 --


def test_encrypt_failure_between_write_and_replace_cleans_up_tmp(age_file_env, monkeypatch):
    # A failure after the temp file is written but before os.replace must
    # never leave a stray ciphertext temp file behind, and the vault file
    # itself must be untouched (mirrors headless/session.py's
    # _export_session_cookies FIX-FIRST 2 cleanup shape from v0.0.3).
    vault_file = age_file_env
    runner = _FakeRunner()

    def failing_replace(src, dst):
        raise OSError("simulated failure between write and replace")

    monkeypatch.setattr(vault.os, "replace", failing_replace)

    with pytest.raises(OSError):
        vault.main(["init"], runner=runner)

    tmp_path = vault_file.parent / f"{vault_file.name}.tmp"
    assert not tmp_path.exists()
    assert not vault_file.exists()


def test_init_sets_mode_0600_on_first_write(age_file_env):
    vault_file = age_file_env
    runner = _FakeRunner()

    exit_code = vault.main(["init"], runner=runner)

    assert exit_code == 0
    mode = vault_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_set_re_encrypt_keeps_mode_0600_after_replace(age_file_env, monkeypatch):
    vault_file = age_file_env
    vault_file.parent.mkdir(parents=True, exist_ok=True)
    vault_file.write_text("existing-ciphertext", encoding="utf-8")
    vault_file.chmod(0o644)  # looser to start, proving the re-encrypt tightens it
    runner = _FakeRunner(decrypt_document={"profile": "keep"})
    monkeypatch.setattr(vault.getpass, "getpass", lambda prompt="": "value")

    exit_code = vault.main(["set", "extra"], runner=runner)

    assert exit_code == 0
    mode = vault_file.stat().st_mode & 0o777
    assert mode == 0o600


# --- v0.0.4.1: get -------------------------------------------------------


def test_get_prints_exactly_the_value(age_file_env, capsys):
    age_file_env.write_bytes(b"fixture-ciphertext")
    runner = _FakeRunner(decrypt_document={"profile": DISTINCTIVE_VALUE})

    exit_code = vault.main(["get", "profile"], runner=runner)

    assert exit_code == 0
    assert runner.calls == [["age", "-d", str(age_file_env)]]
    # get is the one documented exception to never-print-values: stdout is
    # exactly the raw value plus one newline, nothing else.
    assert capsys.readouterr().out == DISTINCTIVE_VALUE + "\n"


def test_get_missing_item_refuses_value_free(age_file_env, capsys):
    age_file_env.write_bytes(b"fixture-ciphertext")
    runner = _FakeRunner(decrypt_document={"other": DISTINCTIVE_VALUE})

    exit_code = vault.main(["get", "profile"], runner=runner)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "REFUSED: item 'profile' not in the vault" in out
    assert DISTINCTIVE_VALUE not in out


def test_get_missing_vault_file_refuses_with_zero_runner_calls(age_file_env, capsys):
    runner = _FakeRunner()

    exit_code = vault.main(["get", "profile"], runner=runner)

    assert exit_code == 1
    assert runner.calls == []
    assert "REFUSED: vault file not found" in capsys.readouterr().out


# --- v0.0.4.2: verify ----------------------------------------------------

TEMPLATE_DOC = {
    "_note": "doc key, ignored",
    "identities": [
        {"type": "self", "first_name": "Test", "licence": {"number": "T555", "state": "MI"}},
        {"type": "spouse", "first_name": "Spouse", "licence": {"number": "T556", "state": "MI"}},
    ],
    "addresses": [
        {"type": "home", "zip": "48000", "currently_insured": "yes", "policy_doc": "/path/x.pdf"},
    ],
    "feature_configs": {"insurance": {"companies": ["progressive"]}},
}


@pytest.fixture
def template_file(monkeypatch, tmp_path):
    """Point vault.REPO_ROOT at a tmp copy so tests never depend on the real
    repo-root template's evolving content."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "profile.template.json").write_text(json.dumps(TEMPLATE_DOC))
    monkeypatch.setattr(vault, "REPO_ROOT", root)
    return root / "profile.template.json"


def _runner_with_profile(age_file_env, profile: object) -> "_FakeRunner":
    age_file_env.write_bytes(b"fixture-ciphertext")
    return _FakeRunner(decrypt_document={"profile": json.dumps(profile)})


def test_verify_clean_profile_matches(age_file_env, template_file, capsys):
    profile = {
        "identities": [
            {"type": "self", "first_name": "A", "licence": {"number": "n", "state": "MI"}},
            {"type": "spouse", "first_name": "B", "licence": {"number": "n2", "state": "MI"}},
        ],
        "addresses": [
            {"type": "home", "zip": "48001", "currently_insured": "yes", "policy_doc": "/p.pdf"},
        ],
        "feature_configs": {"insurance": {"companies": ["progressive", "geico"]}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "profile matches the template" in out


def test_verify_unknown_field_is_error_and_value_free(age_file_env, template_file, capsys):
    profile = {
        "identities": [
            {"type": "self", "first_name": DISTINCTIVE_VALUE, "licnece": {"number": "n", "state": "MI"}},
        ],
        "addresses": [], "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "ERROR  identities[type=self].licnece: unknown field (not in the template)" in out
    assert DISTINCTIVE_VALUE not in out  # field VALUES never print


def test_verify_missing_field_is_warning_only(age_file_env, template_file, capsys):
    profile = {
        "identities": [
            {"type": "self", "licence": {"number": "n", "state": "MI"}},  # first_name absent
            {"type": "spouse", "first_name": "B", "licence": {"number": "n2", "state": "MI"}},
        ],
        "addresses": [
            {"type": "home", "zip": "48001", "currently_insured": "yes", "policy_doc": "/p.pdf"},
        ],
        "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 0  # warnings alone do not fail verify
    assert "WARN  identities[type=self].first_name: field in the template but not in the profile" in out


def test_verify_duplicate_type_is_error(age_file_env, template_file, capsys):
    profile = {
        "identities": [
            {"type": "self", "first_name": "A", "licence": {"number": "n", "state": "MI"}},
            {"type": "self", "first_name": "B", "licence": {"number": "n2", "state": "MI"}},
        ],
        "addresses": [], "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "duplicate 'type' value" in out


def test_verify_missing_type_discriminator_is_error(age_file_env, template_file, capsys):
    profile = {
        "identities": [{"first_name": "A", "licence": {"number": "n", "state": "MI"}}],
        "addresses": [], "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "element has no 'type' discriminator" in out


def test_verify_kind_mismatch_is_error(age_file_env, template_file, capsys):
    profile = {
        "identities": {"type": "self"},  # object where the template has an array
        "addresses": [], "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "ERROR  identities: expected array, found object" in out


def test_verify_scalar_array_rejects_object_elements(age_file_env, template_file, capsys):
    profile = {
        "identities": [], "addresses": [],
        "feature_configs": {"insurance": {"companies": [{"name": "progressive"}]}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "ERROR  feature_configs.insurance.companies[0]: expected a plain value" in out


def test_verify_profile_item_missing_refuses(age_file_env, template_file, capsys):
    age_file_env.write_bytes(b"fixture-ciphertext")
    runner = _FakeRunner(decrypt_document={"other": "x"})
    exit_code = vault.main(["verify"], runner=runner)
    assert exit_code == 1
    assert "REFUSED: item 'profile' not in the vault" in capsys.readouterr().out


def test_verify_template_missing_refuses_before_decrypt(age_file_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(vault, "REPO_ROOT", tmp_path / "empty-root")
    runner = _FakeRunner()
    exit_code = vault.main(["verify"], runner=runner)
    assert exit_code == 1
    assert runner.calls == []  # refused before any decrypt prompt
    assert "REFUSED: template not found" in capsys.readouterr().out


def test_verify_unknown_element_type_checked_against_first_template_element(age_file_env, template_file, capsys):
    profile = {
        "identities": [{"type": "child", "first_name": "C", "licence": {"number": "n", "state": "MI"}}],
        "addresses": [], "feature_configs": {"insurance": {"companies": []}},
    }
    exit_code = vault.main(["verify"], runner=_runner_with_profile(age_file_env, profile))
    out = capsys.readouterr().out
    # a new type the template does not know is not itself an error; its
    # fields are checked against the array's first element template
    assert exit_code == 0
    assert "profile matches the template" in out
