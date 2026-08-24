# Errand Mapping

Headless has no frontend/backend split, so AVF's function map becomes an errand map: one row
per errand script, tracing what it touches and where it stops. Maintain this file whenever an
errand is added, changed, or retired.

| Errand script | Site(s) | Reads | Writes (up to) | Secrets / profile fields | Handoff point (human-only after this) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `scripts/probe.py` | any URL | page title, screenshot | none | none | `n/a (read-only errand)`: `--apply` still performs the handoff with an empty plan, so the Director can seed a login |

`scripts/check_env.py` is a maintenance script, not an errand (see `scripts/README.md`): it opens no
browser window, has no site, and the errand contract (modes, `HANDOFF`) does not apply, so it has no
row here.

## Maintenance Rules

1. **Add**: when a new errand script lands (same commit).
2. **Update**: when an errand's site, fields, secrets, or handoff point changes.
3. **Delete**: when an errand is retired (also remove its `--check` from the gate).
4. **Audit**: every handoff point in this table must match the `HANDOFF` constant declared in
   the script; `--check` output must list the same selectors the row implies.
