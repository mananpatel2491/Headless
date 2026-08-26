"""Repository-wide structural grep checks for spec 005-insurance-quote-comparison
(SC-011, SC-014, SC-015, SC-022). Alongside `tests/test_no_direct_typing.py`'s own
structural-scan convention: these prove an invariant mechanically, across the whole
tree, rather than asserting it only in prose.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HEADLESS_DIR = REPO_ROOT / "headless"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Every fixture value this feature's own test suite uses that would be a
# surprising, distinctive thing to find inside a *shipped* module - never a
# generic placeholder a real module might legitimately also contain (a bare
# "500" or "6" would be far too common to test meaningfully).
_DISTINCTIVE_FIXTURE_VALUES = (
    "Sample Mutual",
    "612.00",
    "1SAMPLE0VIN000001",
    "TOTALLY-DISTINCTIVE-FIXTURE-VALUE",
    "DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR",
)


def _iter_py_files(directory: Path):
    return sorted(directory.rglob("*.py"))


def test_sc011_distinctive_fixture_values_never_appear_in_shipped_modules():
    shipped_files = _iter_py_files(HEADLESS_DIR) + _iter_py_files(SCRIPTS_DIR)
    for path in shipped_files:
        text = path.read_text(encoding="utf-8")
        for value in _DISTINCTIVE_FIXTURE_VALUES:
            assert value not in text, f"{value!r} (a test-fixture value) found in shipped file {path}"


def test_sc014_no_shipped_code_calls_vault_get():
    # SC-014 / spec FR-039: vault.py get's underlying function (cmd_get) is
    # reachable only from scripts/vault.py's own CLI dispatch - never from
    # headless/ or any other errand script.
    shipped_files = [p for p in _iter_py_files(HEADLESS_DIR)] + [
        p for p in _iter_py_files(SCRIPTS_DIR) if p.name != "vault.py"
    ]
    for path in shipped_files:
        text = path.read_text(encoding="utf-8")
        assert "cmd_get" not in text, f"cmd_get referenced outside scripts/vault.py, in {path}"


def test_sc022_no_llm_or_ai_client_import_in_the_comparison_or_extraction_path():
    # SC-022 / spec FR-051: no LLM client, API call, or prompt-construction
    # code exists anywhere in headless/compare.py, headless/policydoc.py, or
    # scripts/policy_extract.py.
    forbidden_tokens = ("openai", "anthropic", "genai", "google.generativeai", "langchain", "cohere")
    targets = [
        HEADLESS_DIR / "compare.py",
        HEADLESS_DIR / "policydoc.py",
        SCRIPTS_DIR / "policy_extract.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_tokens:
            assert token not in text, f"{token!r} found in {path} - no LLM call is ever permitted here"
