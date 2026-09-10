# Research: Google Maps Connector

**Feature**: 010-google-maps-connector | **Date**: 2026-09-09

This document records the recon an implementation session ran on 2026-09-09 against Google's
Maps Grounding Lite MCP server, its own tools/list, and its published pricing page, before this
feature's own code was written, and the seven design decisions (D1-D7) that follow from it.

## Evidence

An unauthenticated `initialize` POST to `https://mapstools.googleapis.com/mcp` already answers
HTTP 200, identifying itself as a `"StatelessServer"` at protocol version `2025-06-18`; an
unauthenticated `tools/list` also succeeds. Authentication is enforced only at `tools/call` - a
call with no key, or a revoked one, returns an HTTP 4xx carrying a public error message (for
example, "API key not valid. Please pass a valid API key.").

`tools/list`, read live on 2026-09-09, names five tools - two more than Google's own
documentation named at the time: `search_places` (required `textQuery`; optional `pageSize` up
to 5, `locationBias`, `regionCode`, `languageCode`, `includeExtendedDetails`), `lookup_weather`
(required `location`), `compute_routes` (required `origin`, `destination`; `DRIVE` or `WALK`),
`resolve_names` (a batch of landmark names or addresses to Place IDs), and `resolve_maps_urls`
(Google Maps URLs to Place IDs). The transport is Streamable HTTP, JSON-RPC 2.0: a client POSTs
`application/json`, accepts `application/json, text/event-stream` back, and a server that hands
back an `Mcp-Session-Id` header expects it echoed on later requests in the same session. The rate
limit is 300 queries per minute per project.

Google's pricing page, read 2026-09-09, prices Maps Grounding Lite as an Essentials SKU (SKU
8CD0-1602-5324): 10,000 free events per month, then $7.00 per 1,000 up to 100,000, $5.95 per
1,000 to 500,000, and lower beyond. The terms state Grounding Lite "must not be used with any
models that use the data input into the model for any model training or improvement."

The MCP registry available inside Claude Code lists no Google Maps connector as of 2026-09-09.
Several community MCP servers exist for Google Maps (`david-pivonka/google-maps-mcp-server`,
`BrendanMartin/google-maps-mcp`, `cablate/mcp-google-map`, and the archived
`@modelcontextprotocol/server-google-maps`), each a third-party process that would hold the API
key itself and would need its own security review before this repository trusted it with a
credential.

## D1. Google's own hosted Grounding Lite server, not a third-party MCP server

**Decision**: register Google's own hosted Maps Grounding Lite server directly in `.mcp.json`.
No third-party MCP server is installed or run.

**Rationale**: a hosted, first-party server means no code to maintain in this repository, no
third-party process ever holding the Director's API key, and official Google terms governing the
whole exchange. The MCP registry inside Claude Code lists no Google Maps connector at all, so
this was never a choice between a registry entry and a hosted server - it was a choice between
Google's own server and one of several community servers.

**Alternatives considered**:

- `david-pivonka/google-maps-mcp-server`, `BrendanMartin/google-maps-mcp`,
  `cablate/mcp-google-map`: rejected for this delivery. Each is a third-party process that would
  run locally, hold the API key in its own process memory or configuration, and need its own
  independent security review (dependency audit, key-handling audit) before this repository could
  trust it - work this delivery does not need to do when Google's own hosted server already
  covers every tool this repository's own brief names.
- The archived `@modelcontextprotocol/server-google-maps`: rejected outright - an archived,
  unmaintained package is a worse security posture than an actively hosted, first-party server.

## D2. A hosted MCP server, not a self-written FastMCP wrapper on the Places API (New)

**Decision**: use Google's hosted MCP endpoint rather than writing and hosting a small MCP server
of this repository's own, wrapping the Places API (New) directly.

**Rationale**: a self-written wrapper would need roughly 150 or more lines to cover the same
three capabilities (search, routes, weather) this repository's brief actually needs, plus its own
test suite, plus its own ongoing maintenance as Google's own API surface changes - all to
reimplement what the hosted server already does for free, under Google's own terms, with zero
code in this repository to keep working.

**Alternatives considered**:

- Writing the wrapper anyway, for full control over the tool surface: rejected for this delivery.
  Revisit only if Grounding Lite's own terms or price change in a way that makes the hosted path
  materially worse than maintaining a wrapper - not a foreseeable near-term concern at this
  repository's own personal volume.

## D3. The key from the environment, never the age vault

**Decision**: `HEADLESS_MAPS_API_KEY` is read from the process environment only
(`scripts/maps_check.py`'s own `main`); the age vault is deliberately not this key's home.

**Rationale**: `age` reads its own passphrase directly from the controlling terminal, by design
(this repository's own `CLAUDE.md` "Secrets and profile data" section already documents this
property as the vault's approval gate for every other secret). Claude Code launches an MCP server
process with no controlling terminal at all - there is nothing for `age` to prompt on. The
macOS Keychain, already a selectable backend for other Headless secrets, plus a login-shell
export, gives the same "the key already lives outside the repository" property without needing an
interactive prompt at launch time.

**Alternatives considered**:

- The age vault, with the key fetched once and exported by a wrapper script before Claude Code
  starts: rejected. It would need a shell wrapper around every way Claude Code itself can be
  launched, adding a maintenance surface this repository has no reason to take on when the
  Keychain already solves the same problem with an ordinary login-shell export.
- `HEADLESS_SECRETS_BACKEND=gcp` (Secret Manager), already selectable for other secrets: rejected
  for this key specifically - an MCP server's own header expansion needs a plain environment
  variable at process-launch time, not a runtime fetch through this repository's own
  `headless/secrets.py` seam, which no errand code path touches for this key at all.

## D4. A restricted key declared in terraform, applied by the Director

**Decision**: `terraform/main.tf` declares the two service enablements
(`apikeys.googleapis.com`, `mapstools.googleapis.com`) and one `google_apikeys_key` resource
restricted, via `restrictions.api_targets.service`, to `mapstools.googleapis.com` only. The
Director reviews `terraform plan` and runs `terraform apply` himself; no resource is created from
the console or an ad-hoc CLI call, per this repository's own Lesson 5.

**Rationale**: an unrestricted key could bill any Google API the project has enabled; restricting
it to one service means a leaked or misused key can only ever bill Maps Grounding Lite calls,
capping the worst case to this one SKU's own pricing. Declaring it in Terraform, rather than
creating it by hand in the Cloud Console, keeps this feature consistent with every other cloud
resource this repository's own constitution requires to be declared as code before it exists.

**Alternatives considered**:

- An unrestricted key, for simplicity: rejected - a single extra `restrictions` block costs
  nothing and meaningfully bounds the blast radius of a leaked key.
- Creating the key by hand in the Cloud Console, skipping Terraform entirely, since this is "just
  one key": rejected outright - this repository's own Lesson 5 requires every cloud resource
  declared as code with a projected cost before it exists, with no exception carved out for a
  resource that happens to be small.

## D5. The live check makes at most one billable call, for a fixed public place

**Decision**: `scripts/maps_check.py`'s own `search` step calls `search_places` for one fixed,
public, well-known place (`PROBE_QUERY = "Detroit Institute of Arts"`), capped to `pageSize: 1`,
and only when a key is present and `--no-search` is absent. The script prints a place count only,
never the place itself.

**Rationale**: a live check that proves the connector works must call at least one tool with the
real key to prove `tools/call`'s own authentication path succeeds, not merely that the
unauthenticated handshake does. Fixing the query to a public landmark, rather than letting the
Director type a query of his own, means the check never sends anything he typed to a third party,
and capping the page size to one keeps the call as cheap as a `search_places` call can be, well
inside the free monthly cap.

**Alternatives considered**:

- Checking only the unauthenticated handshake and `tools/list`, never calling a tool at all:
  rejected - it would leave the one path that actually needs the key (`tools/call`) unproven,
  which is exactly the failure mode ("Claude Code shows a connector as connected before any tool
  is ever called") this script's own docstring names as the reason it exists.
- Letting the Director supply his own test query via a flag: rejected for this delivery. A
  Director-supplied query is closer to a real, personal lookup than a fixed public landmark is,
  and this check's whole purpose is a cheap, repeatable, content-free health proof - not a place
  to explore the API's own search quality.

## D6. `.mcp.json` is project-scoped

**Decision**: the server registration lives in `.mcp.json` at the repository root, committed to
the repository, rather than in a user-level or session-only Claude Code configuration.

**Rationale**: a project-scoped server is offered to every Claude Code session opened in this
repository after one Director approval, matching how every other piece of this repository's own
tooling (scripts, gates, the vault) is meant to work the same way for every session that opens
this repository - no separate per-machine setup step beyond the one-time approval prompt and the
key export.

**Alternatives considered**:

- A user-level (`~/.claude`) registration, outside the repository: rejected - it would work only
  on machines where the Director has set it up by hand, defeating the point of this repository
  being the register the Director's own brief asked for ("Build the Google Maps connector in the
  register (in the repo)").

## D7. No `check_env.py` row for the connector

**Decision**: the connector's own health is checked by `scripts/maps_check.py`, never by adding a
row to `scripts/check_env.py`.

**Rationale**: `check_env.py`'s own gate exits non-zero on anything but every row PASS-ing, and is
run routinely as part of this repository's own environment self-test. The connector is optional -
an unset key is an expected, healthy state (a Director who has not yet provisioned the key), not
a failure this repository's general environment check should ever report as one. A dedicated
script, with its own SKIP semantics for the unset-key case, is the correct shape - matching how
`scripts/activity_scan.py`'s own `--check` is a dedicated probe rather than a `check_env.py` row,
for the same reason (an optional, feature-specific dependency, not a universal precondition).

**Alternatives considered**:

- Adding a `maps` row to `check_env.py` that SKIPs when the key is unset: rejected. It would
  entangle an optional feature's own health with the universal environment gate every session
  runs, for a dependency most runs of this repository never touch at all (no errand calls the
  connector automatically - see spec.md's Out of Scope).
