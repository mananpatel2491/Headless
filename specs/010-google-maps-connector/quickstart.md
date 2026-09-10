# Quickstart: Google Maps Connector

**Feature**: 010-google-maps-connector | **Date**: 2026-09-09

Runnable scenarios that exercise this feature, in the order the Director actually needs them.

## Prerequisites

- From the worktree root, the existing `.venv` (no new dependency).
- `terraform` installed (this Mac already has 1.15.8 at `/opt/homebrew/bin/terraform`, per the
  environment correction recorded in this repository's `MEMORY.md` on 2026-09-09).
- A Google Cloud project the Director already controls, with a billing account linked (Maps
  Platform requires one even inside the free monthly cap).

## Scenario 1: apply the terraform as the Director

```bash
cd terraform
terraform init
terraform plan -var project_id="<your-project-id>"
```

Review the plan: exactly three resources to create (`google_project_service.apikeys`,
`google_project_service.mapstools`, `google_apikeys_key.maps_grounding_lite`), nothing else.

```bash
terraform apply -var project_id="<your-project-id>"
```

Confirm when prompted. Then, once:

```bash
terraform output -raw maps_api_key
```

Copy the printed key string directly into the Keychain (do not paste it anywhere else):

```bash
security add-generic-password -a headless -s maps-api-key -w
```

(paste the key at the prompt). Never write the key string to a file in this repository, a
preview, a log, or a chat message.

## Scenario 2: export the key in the shell

Add this line to `~/.zshrc` (or the equivalent for another shell):

```bash
export HEADLESS_MAPS_API_KEY="$(security find-generic-password -a headless -s maps-api-key -w 2>/dev/null)"
```

Open a new terminal (or `source ~/.zshrc`) so the variable is set. `.mcp.json`'s own
`${HEADLESS_MAPS_API_KEY}` placeholder expands from this environment variable when Claude Code
loads the server - if it is unset, Claude Code warns and loads the server unexpanded, and every
tool call then fails auth.

## Scenario 3: prove the connector with the live check

```bash
python scripts/maps_check.py --no-search
```

Expected: `server PASS`, `tools PASS`, `search SKIP - --no-search given; no billable tool call
was made` (or `search SKIP - HEADLESS_MAPS_API_KEY is not set ...` when the key is not exported
yet), exit 0.

```bash
python scripts/maps_check.py
```

Expected, once the key from Scenario 2 is set: all three rows `PASS`, including `search PASS -
search_places returned <n> result(s)`, exit 0. Exactly one billable `search_places` call is made,
for the fixed public place "Detroit Institute of Arts" - well inside the 10,000 free events per
month.

If the key is wrong or revoked: `FAIL: HTTP 403 on tools/call: <the server's own public error
message>`, exit 1 - the key value itself never appears in the output (the transport replaces it
with `***` mechanically, and a non-JSON error page is never shown at all).

## Scenario 4: approve the project server in Claude Code and ask a session to find a place

Open (or reopen) an interactive Claude Code session in this repository. The first time,
`claude` prompts to approve the project-scoped `google-maps` server - approve it once; every
later session in this repository reuses that approval. (`claude mcp reset-project-choices`
clears every stored project-scoped approval in this repository, including this one, so it is
re-prompted on the next session.)

Then ask the session something like "find a coffee shop near the Detroit Institute of Arts" - it
calls `search_places` on the registered connector directly, with no browser window ever opening,
and returns Place IDs, coordinates, and a Google Maps link.

## Scenario 5: rotate or revoke the key

To rotate: run `terraform apply -replace=google_apikeys_key.maps_grounding_lite -var
project_id="<your-project-id>"` from `terraform/`, then repeat Scenario 1's Keychain step with
the new key string, and open a new login shell so the export picks it up.

To revoke without rotating (stop the connector working until re-provisioned): `terraform destroy
-target=google_apikeys_key.maps_grounding_lite -var project_id="<your-project-id>"` from
`terraform/`, or delete the key from the Cloud Console's API Credentials page directly. Either
way, `python scripts/maps_check.py` then reports `FAIL: HTTP 403 on tools/call: ...` (or an
equivalent denial) until a new key is provisioned and re-exported.

Confirm nothing leaked to the repository:

```bash
git status
```

Expected: clean, or showing only files this delivery's own implementation and documentation
intentionally added - never a `.tfstate` file, a `.tfvars` file, or anything under
`terraform/.terraform/`, all of which stay gitignored.
