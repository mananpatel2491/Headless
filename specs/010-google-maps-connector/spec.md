# Feature Specification: Google Maps Connector (Register Google's Hosted MCP Server)

**Feature Branch**: `v0.0.10` (spec directory `010-google-maps-connector`)

**Created**: 2026-09-09

**Status**: Draft

**Input**: Retro-documentation of the v0.0.10 Google Maps connector. The connector is already
implemented and unit-tested (`headless/mapsmcp.py`, `scripts/maps_check.py`,
`tests/test_maps_check.py`, `.mcp.json`, `terraform/main.tf`, `terraform/variables.tf`,
`terraform/outputs.tf`, 25 tests). This document records what the shipped code does as a Spec
Kit set, written 2026-09-10, one day after the Director's decision and the implementation
(2026-09-09).

## Why

The Director's brief was: "Build the Google Maps connector in the register (in the repo), as I
see in future the repo being used to interact with the web to identify locations." Built after
the activity-scan objective (v0.0.9) was met.

Every prior errand in this repository drives a browser. This feature adds no browser
automation at all. Instead, it registers Google's own hosted Maps Grounding Lite MCP server
(`https://mapstools.googleapis.com/mcp`) with every Claude Code session opened in this
repository, so a future session can identify a location, geocode a name, compute a route, or
read the weather by calling a tool directly - no headless Chrome, no selector, no page to
scrape. The activity scan (v0.0.9) keeps reading the Google Maps list view for its own richer
list data (rating, review count, category, hours); this connector serves a different, narrower
need: quick, structured lookups a future session runs for itself.

Recon 2026-09-09 found no Google Maps connector in this environment's MCP registry, so this
feature registers Google's own hosted server directly, declares the one cloud resource it needs
(a restricted API key) under this repository's Lesson 5 cost gate, and ships a live check
(`scripts/maps_check.py`) so the Director can prove the connector works before relying on it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A future session identifies a location, computes a route, or reads the weather (Priority: P1)

Once the key is set, any Claude Code session opened in this repository can call `search_places`,
`lookup_weather`, `compute_routes`, `resolve_names`, or `resolve_maps_urls` on the registered
`google-maps` server - no browser, no selector, no scraping.

**Why this priority**: this is the feature's whole purpose, stated directly in the Director's own
brief.

**Independent Test**: with `HEADLESS_MAPS_API_KEY` set and the project-scoped server approved,
ask a session to find a public place; confirm it calls `search_places` and receives Place IDs,
coordinates, and a Google Maps link back, with no browser window ever opening.

**Acceptance Scenarios**:

1. **Given** the key is set and the server is approved, **When** a session calls `search_places`
   with a `textQuery`, **Then** it receives AI-generated place summaries with Place IDs,
   coordinates, and Google Maps links, and optionally `pageSize` (up to 5), `locationBias`,
   `regionCode`, `languageCode`, or `includeExtendedDetails`.
2. **Given** the key is set, **When** a session calls `compute_routes` with `origin` and
   `destination`, **Then** it receives a distance and a duration for `DRIVE` or `WALK` (no
   turn-by-turn).
3. **Given** the key is set, **When** a session calls `lookup_weather` with a `location`, **Then**
   it receives current, hourly, and daily weather.
4. **Given** the key is set, **When** a session calls `resolve_names` with a batch of landmark
   names or addresses, or `resolve_maps_urls` with Google Maps URLs, **Then** it receives the
   corresponding Place IDs.

---

### User Story 2 - The Director provisions the key once (Priority: P1)

The Director picks a Google Cloud project, reviews `terraform plan`, applies it, and stores the
resulting restricted key in the macOS Keychain, then exports it from his login shell.

**Why this priority**: no tool call succeeds without the key; provisioning it is the one-time
setup gate every later scenario depends on.

**Independent Test**: from `terraform/`, run `terraform validate`; confirm it passes with
provider `hashicorp/google ~> 6.0` and exactly three resources declared, with no resource ever
created by this test itself.

**Acceptance Scenarios**:

1. **Given** a chosen `project_id` with a billing account linked, **When** the Director runs
   `terraform plan -var project_id=...` from `terraform/`, **Then** the plan shows exactly three
   resources to create: the `apikeys.googleapis.com` enablement, the `mapstools.googleapis.com`
   enablement, and one API key restricted to `mapstools.googleapis.com`.
2. **Given** a reviewed plan, **When** the Director runs `terraform apply`, **Then** Terraform
   creates those three resources and no others, and `terraform output -raw maps_api_key` prints
   the key string once, to the Director's own terminal only.
3. **Given** the key string, **When** the Director stores it (`security add-generic-password -a
   headless -s maps-api-key -w`) and adds the export line to his login shell, **Then**
   `HEADLESS_MAPS_API_KEY` is set in every later login shell, and `.mcp.json`'s
   `${HEADLESS_MAPS_API_KEY}` placeholder expands to it at Claude Code's own load time.

---

### User Story 3 - The Director proves the connector with the live check (Priority: P2)

`scripts/maps_check.py` performs the MCP handshake, lists the tools, and (only when the key is
set and `--no-search` is absent) makes exactly one `search_places` call for a fixed public place,
printing three value-free PASS/FAIL/SKIP rows.

**Why this priority**: this repository's Lesson 4 requires a read-only live check before any
dependency is trusted; the connector is no exception, even though it opens no browser.

**Independent Test**: stub `urllib.request.urlopen` to answer the JSON-RPC handshake and
`tools/list`; assert the printed rows and the exit code match the stub, with never a network
call and never a key value in the captured output.

**Acceptance Scenarios**:

1. **Given** `HEADLESS_MAPS_API_KEY` is unset, **When** the Director runs
   `python scripts/maps_check.py`, **Then** the `server` and `tools` rows print PASS, the
   `search` row prints `SKIP - HEADLESS_MAPS_API_KEY is not set; the handshake needs no key, a
   tool call does`, and the script exits 0 - no `tools/call` request is ever sent.
2. **Given** `HEADLESS_MAPS_API_KEY` is set, **When** the Director runs
   `python scripts/maps_check.py`, **Then** all three rows print PASS, including
   `search PASS - search_places returned <n> result(s)`, and the script exits 0 - exactly one
   billable call is made, for the fixed public place `"Detroit Institute of Arts"`.
3. **Given** any key state, **When** the Director runs `python scripts/maps_check.py
   --no-search`, **Then** the `search` row still prints `SKIP` and no `tools/call` request is
   ever sent, even if the key is set.

### Edge Cases

- **Key unset**: the handshake and `tools/list` need no key (the server is a `StatelessServer`
  answering both unauthenticated); `search` prints `SKIP` and exits 0 as long as `server`/`tools`
  both pass. No tool call is ever attempted without a key.
- **Key revoked or invalid**: a `tools/call` (or any call, if Google ever gates the handshake
  itself) returns an HTTP 4xx; `Transport.call` raises `McpError` carrying only the server's own
  public error message, trimmed to 200 characters (for example, "API key not valid. Please pass
  a valid API key.") - never the key value, never a header. `maps_check.py` prints
  `FAIL: HTTP 403 on tools/call: <that message>` and exits 1.
- **Endpoint down or unreachable**: `urlopen` raises `URLError`, `OSError`, or `TimeoutError`;
  `maps_check.py` prints `FAIL: <ExceptionClassName> reaching the endpoint` (the exception's own
  message and any embedded detail are never printed) and exits 1.
- **A tool missing**: `tools/list`'s own result omits one of `EXPECTED_TOOLS =
  ("search_places", "lookup_weather", "compute_routes")`; the `tools` row prints
  `FAIL - missing <name(s)> (found <names>)` and the script exits 1, even when `server` passed
  and `search` was skipped or passed.
- **A same-session approval prompt**: `.mcp.json` registers a project-scoped server. The first
  interactive Claude Code session opened in this repository after this delivery lands prompts
  the Director to approve `google-maps` once; every later session in this repository reuses that
  approval without prompting again. `claude mcp reset-project-choices` clears every stored
  project-scoped approval in this repository, including this one, so it is re-prompted on the
  next session.
- **The key variable is set but empty or whitespace-only**: `.mcp.json`'s `${HEADLESS_MAPS_API_KEY}`
  expansion is Claude Code's own behavior, not this repository's code; `scripts/maps_check.py`'s own
  `main` reads the variable with `.strip() or None`, so an empty or whitespace-only value counts as
  unset: the `search` row prints `SKIP`, no key header is sent, and no call is attempted.

## Requirements *(mandatory)*

### Functional Requirements

**Registration**

- **FR-001**: `.mcp.json` MUST register exactly one MCP server, named `google-maps`, with
  `"type": "http"`, `"url": "https://mapstools.googleapis.com/mcp"`, and one header,
  `"X-Goog-Api-Key": "${HEADLESS_MAPS_API_KEY}"` - the literal placeholder text, never a real
  key value.
- **FR-002**: The registration MUST be project-scoped (committed to the repository root, not a
  user- or session-scoped config), so every Claude Code session opened in this repository offers
  the connector after one Director approval.

**Message shapes (`headless/mapsmcp.py`, pure, no network I/O)**

- **FR-003**: `build_request(method, params, request_id)` MUST return UTF-8 JSON-RPC 2.0 bytes:
  `{"jsonrpc": "2.0", "method": ...}`, plus `"params"` when given and plus `"id"` when
  `request_id` is not `None` (a `None` id builds a notification, carrying no `"id"` key at all).
- **FR-004**: `initialize_params(version)` MUST return `{"protocolVersion": PROTOCOL_VERSION,
  "capabilities": {}, "clientInfo": {"name": CLIENT_NAME, "version": version}}`, where
  `PROTOCOL_VERSION = "2025-06-18"` and `CLIENT_NAME = "headless-maps-check"`.
- **FR-005**: `search_params(query=PROBE_QUERY)` MUST return a `tools/call` argument object naming
  `"search_places"` with `arguments = {"textQuery": query, "pageSize": 1}` - `pageSize` capped to
  `1` always, and `query` defaulting to the fixed public probe `PROBE_QUERY = "Detroit Institute
  of Arts"`.
- **FR-006**: `parse_response(body, content_type, request_id)` MUST read a JSON-RPC result for
  `request_id` from a plain JSON body (one object or a batch array) or from an SSE stream, where
  one event is the `data:` lines up to a blank line joined with a newline (the SSE continuation
  rule), a JSON array payload is flattened, and a non-JSON event is skipped; MUST raise `McpError`
  on a JSON-RPC error object for that id, on a body that is not JSON, and when no result for that
  id is present.
- **FR-007**: `tool_names(tools_result)` MUST return the `"name"` of every dict entry in
  `tools_result["tools"]` that carries a non-empty name, and MUST return `[]` when `"tools"` is
  absent or not a list. `missing_tools(names)` MUST return every name in `EXPECTED_TOOLS =
  ("search_places", "lookup_weather", "compute_routes")` absent from `names`.
- **FR-008**: `count_places(call_result)` MUST return `len(call_result["structuredContent"]["places"])`
  when that list is present (0 included), None when the call answered with content but no such
  list (the check then prints "answered", never an invented count), 0 when nothing came back, and
  MUST raise `McpError` when the result carries `isError`.
- **FR-009**: `CheckOutcome` MUST be a frozen dataclass (`server`, `protocol`, `tools`, `missing`,
  `places: int | None`) whose `.lines()` MUST return exactly three value-free lines in order -
  `server`, `tools`, `search` - each a fixed-width label followed by `PASS`, `FAIL`, or `SKIP` and
  a short reason, never a place name, an address, or a coordinate. `.ok` MUST be `True` exactly
  when `missing` is empty and `places` is not `0` (that is, `places is None` or `places > 0`).

**The live check (`scripts/maps_check.py`)**

- **FR-010**: `Transport` MUST POST every JSON-RPC body with `Content-Type: application/json`,
  `Accept: application/json, text/event-stream`, and `MCP-Protocol-Version:
  <mapsmcp.PROTOCOL_VERSION>`; it MUST add the `X-Goog-Api-Key` header only when an API key was
  given at construction, and MUST add `Mcp-Session-Id` on every request after the server first
  returns one, reusing that same session id for every later request in the run.
- **FR-011**: An HTTP status of 400 or above on any `Transport.call`/`Transport.notify` MUST raise
  `McpError("HTTP <status> on <method>: <public error text>")`, where the public error text is
  the server's own JSON `"error"."message"` field (trimmed to 200 characters) when the body
  parses as such a JSON object, else the fixed note `(non-JSON error body, <n> bytes, not shown)`;
  the transport MUST replace the key value with `***` in every error text before raising it, so
  a gateway page that quotes the request headers can never surface the key.
- **FR-012**: `run_check(transport, search, has_key)` MUST call, in order: `initialize` (with
  `initialize_params`), the `notifications/initialized` notification, then `tools/list`; MUST
  make exactly one `tools/call` for `search_places` when, and only when, both `search` is `True`
  and `has_key` is `True`; and MUST return a `CheckOutcome` built from those results, with
  `places` left `None` when the search step was skipped.
- **FR-013**: `main` MUST read the key from `os.environ.get(mapsmcp.API_KEY_ENV)` only
  (`API_KEY_ENV = "HEADLESS_MAPS_API_KEY"`) - never a file, never the vault - and MUST fold an
  absent or empty value to `None` (`or None`).
- **FR-014**: `--no-search` MUST suppress the `tools/call` step unconditionally, even when the key
  is set; it MUST NOT change the `server`/`tools` steps in any way.
- **FR-015**: `--endpoint` MUST override `mapsmcp.MCP_ENDPOINT` and MUST be hidden from `--help`
  (`argparse.SUPPRESS`) - a test-only override, never advertised as a supported flag.
- **FR-016**: `main` MUST print `outcome.lines()` (three rows) on any completed run, whether or
  not every row passed, and MUST exit `0` when `outcome.ok` is `True`, else `1`.
- **FR-017**: A `McpError` raised anywhere in `run_check` MUST be caught by `main`, printed as
  `FAIL: <the McpError's own message>`, and MUST exit `1` without printing the three-row summary.
- **FR-018**: A `urllib.error.URLError`, `OSError`, or `TimeoutError` raised anywhere in
  `run_check` MUST be caught by `main`, printed as exactly `FAIL: <ExceptionClassName> reaching
  the endpoint` (no further detail from the exception), and MUST exit `1`.

**Infrastructure (`terraform/`)**

- **FR-019**: `terraform/main.tf` MUST declare exactly three resources on a Director-supplied
  `var.project_id`: `google_project_service.apikeys` (`apikeys.googleapis.com`),
  `google_project_service.mapstools` (`mapstools.googleapis.com`), and
  `google_apikeys_key.maps_grounding_lite`, restricted with `restrictions.api_targets.service =
  "mapstools.googleapis.com"` and depending on both service enablements.
- **FR-020**: `terraform/outputs.tf` MUST declare `maps_api_key` (the key's own `key_string`,
  marked `sensitive = true`) and `mcp_endpoint` (the fixed literal
  `https://mapstools.googleapis.com/mcp`).
- **FR-021**: `terraform validate` MUST pass with provider `hashicorp/google` pinned to `~> 6.0`,
  and `terraform/.terraform.lock.hcl` MUST be committed while `terraform/.terraform/`, every
  `*.tfstate*`, and every `*.tfvars*`/`*.tfvars.json` stay gitignored.
- **FR-022**: No resource declared under `terraform/` MUST ever be created by anyone but the
  Director, and never from the console or an ad-hoc CLI call - only through a reviewed `terraform
  plan` followed by `terraform apply`, both run by the Director.

**Key handling**

- **FR-023**: The key MUST NEVER be written to the repository, `.env`, `.mcp.json` (beyond the
  `${HEADLESS_MAPS_API_KEY}` placeholder), a log, or a preview artifact.
- **FR-024**: The recommended key home MUST be the macOS Keychain (`security
  add-generic-password -a headless -s maps-api-key -w`), exported at login shell start
  (`~/.zshrc`), matching the pattern documented at the end of `.env.example`.
- **FR-025**: The age vault MUST NOT be used for this key - `age` reads its passphrase from the
  controlling terminal, and Claude Code launches an MCP server with no terminal for the key to
  be prompted on.

### Non-Functional Requirements

- **NFR-001**: The default `pytest -q` run MUST exercise every path this feature adds
  (`headless/mapsmcp.py`, `scripts/maps_check.py`) through a stubbed `urllib.request.urlopen` -
  zero real network calls, zero real MCP server contact, zero real API key used.
- **NFR-002**: Every fixture, example, and stub key value in this feature's own document set and
  test suite MUST be an obviously synthetic placeholder (`"k-test"`, `"k-secret-value"`) - no
  real API key value ever appears in code, tests, or documentation; the only key text permitted
  in prose is the literal placeholder `${HEADLESS_MAPS_API_KEY}` or the words "the key".
- **NFR-003**: `scripts/maps_check.py` MUST NEVER print a place name, an address, a coordinate,
  or the key itself - every printed line is value-free by construction (`CheckOutcome.lines()`,
  the fixed error notes, `Transport._redact`, the fixed `ExceptionClassName` line), and a test
  that plants the key in a gateway error page proves the key never reaches stdout.

### Key Entities

- **`CheckOutcome`**: the check's own result shape - `server`, `protocol`, `tools`, `missing`,
  `places` - rendered as three value-free PASS/FAIL/SKIP lines.
- **`Transport`**: one Streamable HTTP MCP connection - the endpoint, an optional API key, the
  server-issued session id once seen, and a monotonically increasing JSON-RPC request id.
- **`McpError`**: a value-free `RuntimeError` carrying only a JSON-RPC error object's own code and
  message, or a transport-shape complaint - never a header value, never the key.
- **The three terraform resources**: two `google_project_service` enablements
  (`apikeys.googleapis.com`, `mapstools.googleapis.com`) and one `google_apikeys_key` restricted
  to `mapstools.googleapis.com`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The full `pytest -q` suite, including this feature's own 25 tests, passes with zero
  real network calls (`urllib.request.urlopen` stubbed throughout `tests/test_maps_check.py`).
- **SC-002**: A unit test proves the transport sends the `X-Goog-Api-Key` header only when a key
  was given, and reuses the server's own `Mcp-Session-Id` on every request after the first one
  that returns it.
- **SC-003**: A unit test proves an HTTP error response becomes a value-free `McpError` whose
  message never contains a key value passed to the transport, even when that key is a
  recognizable placeholder like `"k-secret-value"`.
- **SC-004**: A unit test proves `--no-search` issues no `tools/call` request even when the key
  environment variable is set.
- **SC-005**: A unit test proves the CLI exits `0` with a key and one successful search, `0`
  without a key (the `search` row prints `SKIP`), `1` when `tools/list` omits an expected tool,
  and `1` on a stubbed transport failure whose printed output starts with `FAIL:
  <ExceptionClassName> reaching the endpoint` and never contains the stubbed exception's own
  message text.
- **SC-006**: A live run against the real hosted server (2026-09-09, from this worktree, no key
  set) exits 0 and prints `server PASS - StatelessServer (protocol 2025-06-18)`, `tools PASS -
  search_places, lookup_weather, compute_routes, resolve_names, resolve_maps_urls`, and `search
  SKIP - HEADLESS_MAPS_API_KEY is not set; the handshake needs no key, a tool call does` -
  proving the unauthenticated handshake and `tools/list` really do succeed against the live
  endpoint, matching research.md's per-tool-call authentication model.
- **SC-007**: `terraform validate`, run from `terraform/` in this worktree, passes with provider
  `hashicorp/google ~> 6.0` and exactly the three resources FR-019/FR-020 describe - proving the
  declaration is syntactically and referentially sound without creating anything.

## Assumptions

- Google's Maps Grounding Lite server keeps the tool surface recon observed live on 2026-09-09:
  five tools (`search_places`, `lookup_weather`, `compute_routes`, `resolve_names`,
  `resolve_maps_urls`), two more than Google's own documentation names at the time; this feature
  only requires the three documented ones (`EXPECTED_TOOLS`), so a Google-side removal of either
  undocumented tool does not fail `maps_check.py`.
  authentication is enforced per `tools/call`, never at the handshake (`initialize` and
  `tools/list` both answered live, unauthenticated, with a 200 - the server calls itself a
  `StatelessServer`).
- The Director runs `terraform apply` from his own machine, on a project he already controls,
  with billing already linked or linked before the apply - Maps Platform requires a billing
  account even inside the free monthly cap.
- Claude Code's own `${VAR}` expansion behavior in `.mcp.json` (warn-and-load-unexpanded when the
  variable is unset) is a fact about Claude Code, not something this repository's own code
  controls or tests.
- The rate limit (300 queries per minute per project) and the free cap (10,000 events per month)
  are Google's own published terms as read 2026-09-09; this repository's own usage (one Director,
  occasional lookups, one billable call per live check run) stays far under both.

## Out of Scope

- Any browser automation through this connector - it is a pure API/tool-call path, never a
  Playwright session.
- Letting `scripts/activity_scan.py` or any other errand call the connector automatically - a
  future version may explore this; this delivery does not.
- A `check_env.py` row for the connector (research.md D7) - the connector is optional, and that
  gate exits non-zero on anything but PASS.
- Any secrets backend other than the environment variable for this specific key - not the vault,
  not the Keychain backend already used for other Headless secrets (`HEADLESS_SECRETS_BACKEND`),
  since Claude Code launches the MCP server process itself, outside this repository's own secrets
  seam.
- Rotating or revoking the key automatically - rotation is a Director-run `terraform` or Cloud
  Console action, documented in quickstart.md Scenario 5, never automated by this repository.
