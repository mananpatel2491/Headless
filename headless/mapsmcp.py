"""Google Maps connector: the pure logic behind `scripts/maps_check.py` (spec 010).

Builds and reads the JSON-RPC 2.0 messages the Model Context Protocol's Streamable HTTP
transport carries, for the one hosted server this repository registers in `.mcp.json`:
Google's Maps Grounding Lite at `https://mapstools.googleapis.com/mcp`. Nothing here does
network I/O; the script owns the socket, this module owns the message shapes and the
value-free summaries the check prints.

Value-free by design: no function here ever returns the API key, and the summaries built
from a server response carry counts and tool names only - never a place name, an
address, or a coordinate the Director's own query returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

MCP_ENDPOINT = "https://mapstools.googleapis.com/mcp"
API_KEY_ENV = "HEADLESS_MAPS_API_KEY"
API_KEY_HEADER = "X-Goog-Api-Key"
PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "headless-maps-check"
# A fixed, public, well-known place: the check proves the key works without ever
# sending anything the Director typed.
PROBE_QUERY = "Detroit Institute of Arts"
EXPECTED_TOOLS = ("search_places", "lookup_weather", "compute_routes")


class McpError(RuntimeError):
    """A JSON-RPC error object or a transport shape the check cannot read. Its message
    carries the server's own error code and message text (public API error strings),
    never a header value or the key."""


def build_request(method: str, params: dict | None, request_id: int | None) -> bytes:
    """A JSON-RPC 2.0 request (or a notification when `request_id` is None), UTF-8."""
    message: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    if request_id is not None:
        message["id"] = request_id
    return json.dumps(message).encode("utf-8")


def initialize_params(version: str) -> dict:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": CLIENT_NAME, "version": version},
    }


def search_params(query: str = PROBE_QUERY) -> dict:
    """One `tools/call` for `search_places` (its only required argument is `textQuery`,
    read from the live tools/list on 2026-09-09), capped to one result: the check
    counts, it never reads the place."""
    return {"name": "search_places", "arguments": {"textQuery": query, "pageSize": 1}}


def parse_response(body: str, content_type: str, request_id: int) -> dict:
    """The JSON-RPC result for `request_id` out of a plain JSON body or an SSE stream
    (`data:` lines). Raises McpError on a JSON-RPC error object, a missing result, or
    an unreadable body."""
    messages: list[dict] = []
    if "text/event-stream" in (content_type or ""):
        # One SSE event = the `data:` lines up to a blank line, joined with a
        # newline (the SSE continuation rule); a payload that is a JSON array is
        # flattened the same way the plain-JSON branch below flattens one.
        pending: list[str] = []

        def flush() -> None:
            if not pending:
                return
            payload = "\n".join(pending).strip()
            pending.clear()
            if not payload:
                return
            try:
                decoded = json.loads(payload)
            except ValueError:
                return
            messages.extend(decoded if isinstance(decoded, list) else [decoded])

        for raw in body.splitlines():
            line = raw.rstrip("\r")
            if line.strip() == "":
                flush()
            elif line.startswith("data:"):
                pending.append(line[len("data:"):].lstrip())
        flush()
    else:
        try:
            decoded = json.loads(body) if body.strip() else {}
        except ValueError as exc:
            raise McpError("response body is not JSON") from exc
        messages = decoded if isinstance(decoded, list) else [decoded]
    for message in messages:
        if not isinstance(message, dict) or message.get("id") != request_id:
            continue
        if "error" in message:
            error = message["error"] or {}
            raise McpError(f"JSON-RPC error {error.get('code')}: {error.get('message', '')}"[:300])
        if "result" in message:
            return message["result"]
    raise McpError(f"no result for request {request_id} in the response")


def tool_names(tools_result: dict) -> list[str]:
    tools = tools_result.get("tools") if isinstance(tools_result, dict) else None
    if not isinstance(tools, list):
        return []
    return [str(tool.get("name", "")) for tool in tools if isinstance(tool, dict) and tool.get("name")]


def missing_tools(names: list[str]) -> list[str]:
    return [name for name in EXPECTED_TOOLS if name not in names]


def count_places(call_result: dict) -> int | None:
    """How many places a `search_places` call returned - a count only, read from
    `structuredContent.places` when the server sends that shape. None when the
    call answered with content but no structured place list (the check reports
    "answered", never a made-up count); 0 when nothing came back at all. The
    text content block is never parsed for place data."""
    if not isinstance(call_result, dict):
        return 0
    if call_result.get("isError"):
        raise McpError("search_places reported an error result")
    structured = call_result.get("structuredContent")
    if isinstance(structured, dict):
        places = structured.get("places")
        if isinstance(places, list):
            return len(places)
    content = call_result.get("content")
    if isinstance(content, list) and content:
        return None
    return 0


# Why the search row was skipped (the check never guesses): the key is absent, or the
# Director asked for no billable call.
SKIP_NO_KEY = "no_key"
SKIP_NO_SEARCH = "no_search"


@dataclass(frozen=True)
class CheckOutcome:
    server: str
    protocol: str
    tools: list[str]
    missing: list[str]
    places: int | None  # a structured count; None when unstructured or skipped
    skipped: str | None = None  # SKIP_NO_KEY | SKIP_NO_SEARCH | None (a call was made)

    def lines(self) -> list[str]:
        out = [f"server       PASS - {self.server} (protocol {self.protocol})"]
        if self.missing:
            out.append(f"tools        FAIL - missing {', '.join(self.missing)} (found {', '.join(self.tools) or 'none'})")
        else:
            out.append(f"tools        PASS - {', '.join(self.tools)}")
        if self.skipped == SKIP_NO_KEY:
            out.append(f"search       SKIP - {API_KEY_ENV} is not set; the handshake needs no key, a tool call does")
        elif self.skipped == SKIP_NO_SEARCH:
            out.append("search       SKIP - --no-search given; no billable tool call was made")
        elif self.places is None:
            out.append("search       PASS - search_places answered (no structured place count in this response)")
        elif self.places > 0:
            out.append(f"search       PASS - search_places returned {self.places} result(s)")
        else:
            out.append("search       FAIL - search_places returned no result")
        return out

    @property
    def ok(self) -> bool:
        return not self.missing and self.places != 0
