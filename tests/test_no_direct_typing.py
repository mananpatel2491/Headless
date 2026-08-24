"""Structural test (FIX-FIRST 10+11, N9): no errand script types directly.

`Session.fill` is the only sanctioned way to type into a page; a `FieldPlan`
value can only come from the registry, the vault, or a literal declared in
the script. This test proves that invariant mechanically by parsing every
`scripts/*.py` and flagging any `ast.Call` whose function is an attribute
access (`<anything>.fill(...)`, `.type(`, `.press(`, `.click(`,
`.select_option(`, `.check(`, `.dblclick(`, `.set_input_files(`) - any such
call on a page or locator in an errand script would be a way to type (or
trigger a click/upload) that bypasses the registry/vault/literal path
entirely, so it fails the commit gate.

An AST walk (rather than a line regex) is deliberate: it only ever matches
real call expressions, so a docstring or comment that happens to mention
"session.fill(...)" in prose is never flagged.

`verify_structure.py` (filesystem-only, no page) and `check_env.py` (opens no
browser window - see PATTERNS.md/contracts) are excluded: they have no page
or locator to type into in the first place.
"""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

EXCLUDED = {"verify_structure.py", "check_env.py"}

FORBIDDEN_ATTRS = {"fill", "type", "press", "click", "select_option", "check", "dblclick", "set_input_files"}


def _errand_script_paths() -> list[Path]:
    return [path for path in sorted(SCRIPTS_DIR.glob("*.py")) if path.name not in EXCLUDED]


def _find_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_ATTRS:
            violations.append(f"{path.relative_to(SCRIPTS_DIR.parent)}:{node.lineno}: .{func.attr}(...) call")
    return violations


def test_at_least_one_errand_script_is_scanned():
    # Guards against this test silently scanning nothing if scripts/ changes shape.
    assert _errand_script_paths(), "expected at least one errand script under scripts/"


def test_no_direct_typing_or_clicking_in_errand_scripts():
    violations = []
    for path in _errand_script_paths():
        violations.extend(_find_violations(path))

    assert not violations, "direct typing/clicking found outside Session.fill:\n" + "\n".join(violations)


def test_a_docstring_mentioning_fill_is_not_flagged(tmp_path):
    # Proves the AST approach (vs. a line regex) doesn't false-positive on
    # prose: a comment/docstring naming "locator.fill(" must never trigger.
    decoy = tmp_path / "decoy.py"
    decoy.write_text(
        '"""This script never calls locator.fill(value) directly - see session.fill()."""\n'
        "# also never do page.click(x) here, use Session.fill instead\n"
        "x = 1\n",
        encoding="utf-8",
    )
    assert _find_violations(decoy) == []
