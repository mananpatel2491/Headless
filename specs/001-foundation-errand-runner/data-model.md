# Data Model: Foundation Errand Runner

**Feature**: 001-foundation-errand-runner | **Date**: 2026-08-24

No database. Every entity below is an in-memory Python object; the only persisted data are
the vault items (secrets and the profile document), the Chrome profile directory, and the
preview artifacts.

## Config

| Field | Type | Source | Rules |
| :--- | :--- | :--- | :--- |
| `profile_dir` | Path | `HEADLESS_PROFILE_DIR`, `--profile-dir` | `~` expanded; created on first launch |
| `headed` | bool | `HEADLESS_HEADED` (default 1), `--headless` | apply requires `True` |
| `cdp_url` | str or None | `HEADLESS_CDP_URL` | when set, attach instead of launch |
| `secrets_backend` | `"keychain"` or `"gcp"` | `HEADLESS_SECRETS_BACKEND` (default keychain) | any other value is a `ConfigError` |
| `keychain_account` | str | `HEADLESS_KEYCHAIN_ACCOUNT` (default `headless`) | |
| `gcp_project` | str or None | `HEADLESS_GCP_PROJECT` | required when backend is `gcp`, else `ConfigError` |
| `preview_dir` | Path | `HEADLESS_PREVIEW_DIR` (default `previews`), `--preview-dir` | created on first write |

Validation happens in `load_config()` before any browser or vault call (FR-004, SC-006).

## Mode

Enumeration `preview | apply | check`, resolved by `resolve_mode(args, isatty, headed)`:

| Flags | isatty | headed | Result |
| :--- | :--- | :--- | :--- |
| none | any | any | `preview` |
| `--check` | any | any | `check` |
| `--apply` | true | true | `apply` |
| `--apply` | false | any | `GateRefused("apply needs an interactive terminal")` |
| `--apply` | true | false | `GateRefused("apply needs a visible browser")` |
| `--apply --check` | | | argparse error (mutually exclusive) |

There is no fourth value. No helper accepts a "submit" or "otp" concept (FR-007).

## FieldPlan

One planned form interaction.

| Field | Type | Rules |
| :--- | :--- | :--- |
| `name` | str | human label shown in previews |
| `selector` | str | Playwright selector |
| `source` | `Source` | exactly one of `registry:<dotted>`, `secret:<item>`, `literal:<text>` |
| `kind` | `"fill"` or `"select"` or `"check"` | how the value is applied |

Resolution: `registry:` reads the profile registry by dotted path (missing path refused);
`secret:` reads the vault; `literal:` is the constant itself. Masking in previews: registry
and secret values masked; literal shown.

## Errand

| Field | Type | Rules |
| :--- | :--- | :--- |
| `name` | str | script stem, used in artifact names |
| `handoff` | str | the `HANDOFF` constant; required, non-empty |
| `plan` | list of `FieldPlan` | what apply would type, in order |
| `dependencies` | list of selectors | what `--check` must resolve |

## Session

| Field | Type | Rules |
| :--- | :--- | :--- |
| `config` | Config | |
| `mode` | Mode | |
| `context` | Playwright BrowserContext | launched (persistent) or attached (CDP) |
| `page` | Playwright Page | one page per run |

Behaviour: `goto(url)` retries once on a transient navigation error; `fill(plan)` never
retries and is refused unless `mode == apply`; `probe(selectors)` returns found/missing per
selector without typing; `handoff()` prints "Your turn", waits for the Director, then closes
and reports whether the window was already closed.

## Vault (secrets backend)

Interface: `get_secret(name) -> str` (raises `SecretMissing(name)`), `put_secret(name,
value)`, `delete_secret(name)`, `self_test() -> bool`.

Implementations: `KeychainBackend(account)`, `GcpBackend(project, client=None)`. Selected by
`Config.secrets_backend`.

## ProfileRegistry

Loaded from the vault item `profile` (JSON object). `get(dotted_path) -> str` raises
`RegistryMissing(path)` for absent paths and refuses non-scalar results. No write API from
scripts (the Director edits the document through `scripts/profile_put.py` or the vault
directly; out of scope for this feature beyond documenting the item name).

## PreviewRecord and artifact

| Field | Type | Rules |
| :--- | :--- | :--- |
| `errand` | str | |
| `mode` | str | |
| `url` | str | final page URL |
| `title` | str | page title |
| `timestamp_utc` | str | `YYYYMMDDTHHMMSSZ` |
| `handoff` | str | |
| `fields` | list of `{name, selector, source_kind, value_masked}` | values masked at construction |
| `checks` | list of `{selector, found}` | present in check mode |

Artifact paths: `<preview_dir>/<errand>-<timestamp_utc>.png` and `.json`. SC-002: no raw
registry or secret value can reach the record because masking happens in the constructor.

## State transitions (one run)

```text
load_config -> resolve_mode -> (apply only) verify vault items exist
   -> open session (launch or attach) -> goto
   -> preview: plan -> record -> artifact -> close
   -> check:   probe dependencies -> record -> artifact -> close
   -> apply:   fill each FieldPlan -> record -> artifact -> handoff -> close
```

Failure before "open session" opens no window (FR-004, SC-006).
