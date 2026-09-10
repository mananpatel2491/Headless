# Contracts: Google Maps Connector

**Feature**: 010-google-maps-connector | **Date**: 2026-09-09

Three stable interfaces: the **`.mcp.json` registration contract**, the **live check's CLI
contract** (every flag, every exit code, every stdout line), and the **terraform I/O contract**.

## 1. `.mcp.json` registration contract

```json
{
  "mcpServers": {
    "google-maps": {
      "type": "http",
      "url": "https://mapstools.googleapis.com/mcp",
      "headers": {
        "X-Goog-Api-Key": "${HEADLESS_MAPS_API_KEY}"
      }
    }
  }
}
```

| Property | Value | Notes |
| :--- | :--- | :--- |
| Server name | `google-maps` | The key under `mcpServers` |
| `type` | `"http"` | Streamable HTTP transport |
| `url` | `"https://mapstools.googleapis.com/mcp"` | Fixed; matches `mapsmcp.MCP_ENDPOINT` |
| `headers["X-Goog-Api-Key"]` | `"${HEADLESS_MAPS_API_KEY}"` | The literal placeholder text - Claude Code expands `${VAR}` from the environment at load; unset warns and loads the server unexpanded, and every tool call then fails auth |
| Scope | Project (committed to the repository root) | Every session opened in this repository offers the connector after one Director approval; `claude mcp reset-project-choices` resets every stored project-scoped approval |

## 2. Live check CLI contract (`scripts/maps_check.py`)

### 2.1 Flags

| Flag | Required | Default | Behavior |
| :--- | :--- | :--- | :--- |
| `--no-search` | No | `False` | Skip the `tools/call search_places` step unconditionally, even when the key is set; never changes the `server`/`tools` steps |
| `--endpoint` | No (hidden, `argparse.SUPPRESS`) | `mapsmcp.MCP_ENDPOINT` | Test-only override of the MCP endpoint URL |

No `--apply`, `--check`, `--show`, or `--profile-dir` flag exists - this is not a browser errand
and the errand contract (`scripts/README.md`) does not apply.

### 2.2 Stdout lines

| Line | When |
| :--- | :--- |
| `server       PASS - <server name> (protocol <version>)` | Always, on a completed run - a successful `initialize` is a precondition of reaching this line at all |
| `tools        PASS - <name, name, ...>` | Every name in `EXPECTED_TOOLS` was present in `tools/list`'s own result |
| `tools        FAIL - missing <name, ...> (found <name, ... or 'none'>)` | At least one expected tool was absent |
| `search       SKIP - HEADLESS_MAPS_API_KEY is not set; the handshake needs no key, a tool call does` | The key was unset or blank (whitespace counts as unset), whatever `--no-search` says |
| `search       SKIP - --no-search given; no billable tool call was made` | The key was set and `--no-search` was given |
| `search       PASS - search_places returned <n> result(s)` | The key was set, `--no-search` was absent, and the call returned a `structuredContent.places` list with at least one entry |
| `search       PASS - search_places answered (no structured place count in this response)` | The call answered with content but no `structuredContent.places` list - the check reports the answer, never an invented count |
| `search       FAIL - search_places returned no result` | The key was set, `--no-search` was absent, and the call returned an empty structured list or no content at all |
| `FAIL: <the McpError's own message>` | An `McpError` was raised anywhere in `run_check` (a JSON-RPC error object, an unreadable response body, or an HTTP status >= 400 with the server's own public error text) - printed alone, replacing the three-row summary, before exit 1 |
| `FAIL: <ExceptionClassName> reaching the endpoint` | A `urllib.error.URLError`, `OSError`, or `TimeoutError` was raised anywhere in `run_check` - no further exception detail is ever printed |

Every line above is value-free: no place name, no address, no coordinate, and no header or key
value ever appears in any of them. The key value is removed mechanically (`Transport._redact`
replaces it with `***`) from every error text before the error is raised, and a non-JSON error
body (a gateway or proxy page, which can quote the request headers back) is never shown at all -
only its byte length is. A test plants the key in such a page and proves it never reaches stdout.

### 2.3 Run sequence

1. Read `HEADLESS_MAPS_API_KEY` from the environment (`os.environ.get(...) or None` - an unset or
   empty value both fold to `None`).
2. Construct a `Transport` for `args.endpoint` (default `mapsmcp.MCP_ENDPOINT`) with that key.
3. `initialize` (params from `initialize_params(VERSION)`), read `serverInfo.name` and
   `protocolVersion`.
4. `notifications/initialized` (a notification, no id, no response body expected).
5. `tools/list` (empty params), read tool names via `tool_names`, compute `missing_tools`.
6. When `--no-search` is absent AND a key is present: exactly one `tools/call` for
   `search_params()` (fixed public query, `pageSize: 1`); count places via `count_places`.
   Otherwise: `places` stays `None`.
7. Build a `CheckOutcome`, print its three lines, exit `0` when `.ok` is `True`, else `1`.
8. Any `McpError` raised during steps 3-6 is caught, printed as `FAIL: <message>`, exit `1`. Any
   `URLError`/`OSError`/`TimeoutError` raised during the same steps is caught, printed as
   `FAIL: <ExceptionClassName> reaching the endpoint`, exit `1`.

### 2.4 Exit codes

| Code | Meaning |
| :--- | :--- |
| `0` | Every printed row is `PASS` or `SKIP` |
| `1` | At least one row is `FAIL`, or an `McpError`/transport error ended the run early |
| `2` | An `argparse` usage error |

### 2.5 Transport-level contract

- Every POST carries `Content-Type: application/json`, `Accept: application/json,
  text/event-stream`, and `MCP-Protocol-Version: <the version the server negotiated in initialize>`
  (`mapsmcp.PROTOCOL_VERSION` until `initialize` has answered).
- `X-Goog-Api-Key` is added only when a key was given at `Transport` construction.
- `Mcp-Session-Id` is added on every request once the server has returned one, reusing the same
  value for the rest of the run.
- An HTTP status >= 400 raises `McpError("HTTP <status> on <method>: <public error text>")`,
  where the public error text is the response body's own `"error"."message"` field (trimmed to 200
  characters) when the body parses as such a JSON object, else the fixed note
  `(non-JSON error body, <n> bytes, not shown)`; in both cases the key value, if present, is
  replaced by `***` before the error is raised.

## 3. Terraform I/O contract

### 3.1 Input

| Variable | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `project_id` | `string` | Yes | The Google Cloud project holding the two service enablements and the restricted key; a billing account must already be linked |

### 3.2 Resources

| Resource | Address | What it declares |
| :--- | :--- | :--- |
| API Keys service enablement | `google_project_service.apikeys` | `apikeys.googleapis.com` on `var.project_id` |
| Maps Grounding Lite enablement | `google_project_service.mapstools` | `mapstools.googleapis.com` on `var.project_id` |
| The restricted key | `google_apikeys_key.maps_grounding_lite` | `restrictions.api_targets.service = "mapstools.googleapis.com"`; `depends_on` both enablements above |

### 3.3 Outputs

| Output | Sensitive | Value |
| :--- | :--- | :--- |
| `maps_api_key` | Yes | `google_apikeys_key.maps_grounding_lite.key_string` |
| `mcp_endpoint` | No | The fixed literal `https://mapstools.googleapis.com/mcp` |

### 3.4 Apply contract

- Only the Director runs `terraform plan` and `terraform apply`, both from `terraform/`, both
  reviewed before applying.
- No resource under `terraform/` is ever created from the console or an ad-hoc CLI call.
- `terraform output -raw maps_api_key` is the only sanctioned way to read the key string; it is
  read once, stored in the macOS Keychain, and never written to a file in this repository.
- `terraform/.terraform/`, every `*.tfstate*`, and every `*.tfvars*`/`*.tfvars.json` stay
  gitignored; `terraform/.terraform.lock.hcl` is committed.
