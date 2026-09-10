# Data Model: Google Maps Connector

**Feature**: 010-google-maps-connector | **Date**: 2026-09-09

No database, no vault item, no profile field, no report file. Everything below is either a
JSON-RPC message shape exchanged over one HTTP connection for the lifetime of one
`scripts/maps_check.py` invocation, or a Terraform resource the Director applies once.

## The JSON-RPC message shapes (`headless/mapsmcp.py`)

### Request / notification (`build_request`)

```text
{"jsonrpc": "2.0", "method": "<method>"}                                   # notification (no id)
{"jsonrpc": "2.0", "method": "<method>", "params": {...}}                  # notification, with params
{"jsonrpc": "2.0", "method": "<method>", "id": <int>}                      # request, no params
{"jsonrpc": "2.0", "method": "<method>", "params": {...}, "id": <int>}     # request, with params
```

| Field | Present when |
| :--- | :--- |
| `jsonrpc` | Always `"2.0"` |
| `method` | Always |
| `params` | `params` argument is not `None` |
| `id` | `request_id` argument is not `None` - its absence is what makes a message a notification |

### `initialize` params (`initialize_params(version)`)

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {},
  "clientInfo": {"name": "headless-maps-check", "version": "<VERSION>"}
}
```

### `tools/call search_places` params (`search_params(query=PROBE_QUERY)`)

```json
{"name": "search_places", "arguments": {"textQuery": "Detroit Institute of Arts", "pageSize": 1}}
```

`pageSize` is always `1`; `query` defaults to the fixed public probe and is never a
Director-typed value.

### Response (`parse_response`)

Two body shapes carry the same JSON-RPC result-or-error object:

| Shape | `content_type` | Read as |
| :--- | :--- | :--- |
| Plain JSON | anything not containing `"text/event-stream"` | One object, or a batch array of objects |
| SSE stream | contains `"text/event-stream"` | Each event's `data:` lines (up to a blank line) joined with a newline and parsed as one JSON payload; an array payload is flattened; a non-JSON event is skipped |

Both shapes are scanned for the first message whose own `"id"` matches the request id passed in.
A matched message carrying `"error"` raises `McpError`; one carrying no `"result"` and no
`"error"` is treated as not matching; no match at all (after scanning every message) also raises
`McpError`.

### `CheckOutcome`

```text
CheckOutcome(
    server: str,             # init.serverInfo.name, or "?"
    protocol: str,            # init.protocolVersion, or "?"
    tools: list[str],         # tool_names(tools/list result)
    missing: list[str],       # missing_tools(tools) - subset of EXPECTED_TOOLS
    places: int | None,       # count_places(tools/call result), or None when search was skipped
)
```

| Field | Drives |
| :--- | :--- |
| `server`, `protocol` | The `server` row: always `PASS` (a successful `initialize` is a precondition of reaching this point at all) |
| `tools`, `missing` | The `tools` row: `PASS` when `missing` is empty, else `FAIL - missing <names> (found <names>)` |
| `places` | The `search` row: `SKIP` when `None`, `PASS - search_places returned <n> result(s)` when `> 0`, `FAIL - search_places returned no result` when `0` |
| `.ok` | `True` when `missing` is empty AND `places != 0` (that is, `None` or positive) |

## The three-row stdout output

```text
server       PASS - StatelessServer (protocol 2025-06-18)
tools        PASS - search_places, lookup_weather, compute_routes, resolve_names, resolve_maps_urls
search       SKIP - HEADLESS_MAPS_API_KEY is not set; the handshake needs no key, a tool call does
```

Exactly three lines, always in this order, on every completed run (a run that raises `McpError`
or a transport error before completion prints one `FAIL: ...` line instead and never reaches
`outcome.lines()` at all).

## The terraform resources

```text
google_project_service.apikeys      # apikeys.googleapis.com
google_project_service.mapstools    # mapstools.googleapis.com (Maps Grounding Lite)
google_apikeys_key.maps_grounding_lite
    restrictions.api_targets.service = "mapstools.googleapis.com"
    depends_on = [apikeys, mapstools]
```

| Input | Type | Notes |
| :--- | :--- | :--- |
| `var.project_id` | `string` | The Google Cloud project; billing must already be linked |

| Output | Sensitivity | Value |
| :--- | :--- | :--- |
| `maps_api_key` | `sensitive = true` | `google_apikeys_key.maps_grounding_lite.key_string` - read once with `terraform output -raw maps_api_key` |
| `mcp_endpoint` | not sensitive | the fixed literal `https://mapstools.googleapis.com/mcp` |

No other resource, output, or variable exists under `terraform/` for this feature.
