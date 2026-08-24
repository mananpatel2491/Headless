# Agentic Skills (scripts/)

Two kinds of script live here: **maintenance** scripts that keep the repo honest, and
**errand** scripts that drive a site on the Director's behalf. Both follow the
Automation-First CLI pattern (`PATTERNS.md`): `argparse`, safe preview by default, runnable
from cron or CI.

## Maintenance

| Script | Description |
| :--- | :--- |
| `verify_structure.py` | Fails (exit 1) when a file on disk is missing from the `Project_Structure.md` Changelog. Part of the commit gate. `--dry-run` prints a read-only notice. |

## Errands

| Script | Description |
| :--- | :--- |
| *(none yet)* | Errand scripts arrive with spec 001 (`check_env.py`, `probe.py`). Each is documented here and in `Function_Mapping.md` in the same commit. |

## Errand contract

Every errand script:

1. Opens with a docstring stating the site, the background, the handoff point, and the
   secrets and profile fields it needs.
2. Declares `HANDOFF = "<the step the human takes>"` as a module constant.
3. Runs in **preview** mode with no flags (no site writes; artifact under `previews/`),
   in **check** mode with `--check` (read-only selector probe), and in **apply** mode with
   `--apply` (fills up to `HANDOFF`, then leaves the window open and prints "Your turn").
4. Never implements a submit, pay, e-verify, or OTP step.
