# Errand Mapping

Headless has no frontend/backend split, so AVF's function map becomes an errand map: one row
per errand script, tracing what it touches and where it stops. Maintain this file whenever an
errand is added, changed, or retired.

| Errand script | Site(s) | Reads | Writes (up to) | Secrets / profile fields | Handoff point (human-only after this) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `scripts/probe.py` | any URL | page title, screenshot | none | none | `n/a (read-only errand)`: `--apply` still performs the handoff with an empty plan, so the Director can seed a login |
| `headless/insurers/progressive.py`'s `ProgressiveQuoteErrand` (composed by `scripts/quote_compare.py`, not run directly) | `https://www.progressive.com/auto/` | the landing page's ZIP field and quote-start button, confirmed twice (before this feature was scoped, and again by implementation-time recon, research.md D8) | the ZIP field and the quote-start click only - implementation-time recon (three headless, scratch-profile, synthetic-data-only walks) found Progressive's own funnel refuses the automated quote-start submission under headless Chrome (three "403 Forbidden" resource-load errors, no navigation past the landing page in any of the three attempts); no selector past the landing page ships this delivery (FR-032) | `registry:addresses.home.zip` | `HANDOFF` (`ProgressiveQuoteErrand.HANDOFF`, `headless/insurers/progressive.py`): explains that recon could not verify anything past the quote-start click, so nothing further is automated - continuing the quote by hand in the window is optional, not required |

`scripts/check_env.py` is a maintenance script, not an errand (see `scripts/README.md`): it opens no
browser window, has no site, and the errand contract (modes, `HANDOFF`) does not apply, so it has no
row here. `scripts/quote_compare.py` (spec 005-insurance-quote-comparison) is an **orchestrator**,
not an errand: it composes `ProgressiveQuoteErrand`'s own `.run()` call (and any future insurer's,
via `headless.insurers.WALK_REGISTRY`) rather than owning a site, a `plan()`/`walk()`, or a
`HANDOFF` of its own - see `scripts/README.md`'s own "Orchestrators" section for its row.
`scripts/policy_extract.py` is a maintenance-adjacent script, not an errand either (no browser, no
site) - see `scripts/README.md`'s Maintenance table.

## Maintenance Rules

1. **Add**: when a new errand script lands (same commit).
2. **Update**: when an errand's site, fields, secrets, or handoff point changes.
3. **Delete**: when an errand is retired (also remove its `--check` from the gate).
4. **Audit**: every handoff point in this table must match the `HANDOFF` constant declared in
   the script; `--check` output must list the same selectors the row implies.
