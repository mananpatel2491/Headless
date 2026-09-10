#!/usr/bin/env python3
"""maps_check: prove the Google Maps connector this repository registers actually answers.

Background (spec 010-google-maps-connector): `.mcp.json` at the repository root registers
Google's hosted Maps Grounding Lite MCP server for every Claude Code session opened here,
with the API key expanded from the `HEADLESS_MAPS_API_KEY` environment variable. Claude
Code shows a connector as connected before any tool is ever called, so a wrong or
unrestricted key would only surface mid-task. This script is the Lesson 4 live check for
that dependency: it performs the MCP handshake, lists the tools, and (when the key is set)
makes one `search_places` call for a fixed public place, printing counts and names only.

Not a browser errand: opens no window, has no preview/apply/check modes, no `HANDOFF`.
Site: `https://mapstools.googleapis.com/mcp` (Streamable HTTP, JSON-RPC 2.0).
Reads: the server's `initialize` result, its `tools/list`, and the shape of one
`tools/call` result. Never prints a place name, an address, a coordinate, or the key.
Writes: nothing, anywhere.
Secrets: `HEADLESS_MAPS_API_KEY` from the environment only - never read from a file, never
from the vault (an MCP server is launched by Claude Code without a terminal, so the key
must already be in the environment; the Director exports it from the Keychain at login).

Usage:
    python scripts/maps_check.py            # handshake + tools/list, plus one search when the key is set
    python scripts/maps_check.py --no-search  # handshake + tools/list only, never a billable call

Exit codes: 0 every row PASS or SKIP; 1 a FAIL row or a transport/JSON-RPC error; 2 a usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless import mapsmcp

VERSION = "0.0.10"
TIMEOUT_SECONDS = 30


class Transport:
    """One Streamable HTTP MCP connection: POSTs JSON-RPC bodies, keeps the session id
    the server may hand back, never logs a header."""

    def __init__(self, endpoint: str, api_key: str | None) -> None:
        self.endpoint = endpoint
        self._api_key = api_key
        self._session_id: str | None = None
        self._next_id = 1
        # The version the server negotiated in `initialize`; sent on every later
        # request (the transport header must match what the server agreed to).
        self.protocol_version = mapsmcp.PROTOCOL_VERSION

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol_version,
        }
        if self._api_key:
            headers[mapsmcp.API_KEY_HEADER] = self._api_key
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, body: bytes) -> tuple[int, str, str]:
        request = urllib.request.Request(self.endpoint, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self._session_id = session
                return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", text

    def _redact(self, text: str) -> str:
        """The one mechanical guarantee this script makes about its output: the key
        value never appears in it, whatever a proxy or gateway echoes back (a
        gateway error page can quote the request line and its headers verbatim)."""
        if self._api_key:
            return text.replace(self._api_key, "***")
        return text

    def call(self, method: str, params: dict | None = None) -> dict:
        request_id = self._next_id
        self._next_id += 1
        status, content_type, text = self._post(mapsmcp.build_request(method, params, request_id))
        if status >= 400:
            raise mapsmcp.McpError(f"HTTP {status} on {method}: {self._redact(_public_error_text(text))}")
        try:
            return mapsmcp.parse_response(text, content_type, request_id)
        except mapsmcp.McpError as exc:
            raise mapsmcp.McpError(self._redact(str(exc))) from None

    def notify(self, method: str, params: dict | None = None) -> None:
        status, _content_type, text = self._post(mapsmcp.build_request(method, params, None))
        if status >= 400:
            raise mapsmcp.McpError(f"HTTP {status} on {method}: {self._redact(_public_error_text(text))}")


def _public_error_text(body: str) -> str:
    """The server's own error message when the body is a Google API error object
    (a public string such as "API key not valid. Please pass a valid API key."),
    trimmed to 200 characters. Any other body shape - an HTML gateway page, plain
    text, a bare string - is never echoed: only its length is reported, because
    such a page can quote the request headers back."""
    try:
        data = json.loads(body)
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message", ""))[:200]
    except ValueError:
        pass
    return f"(non-JSON error body, {len(body.encode('utf-8'))} bytes, not shown)"


def run_check(transport: Transport, *, search: bool, has_key: bool) -> mapsmcp.CheckOutcome:
    init = transport.call("initialize", mapsmcp.initialize_params(VERSION))
    server_info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
    negotiated = str(init.get("protocolVersion", "")) if isinstance(init, dict) else ""
    if negotiated:
        transport.protocol_version = negotiated
    transport.notify("notifications/initialized")
    tools = mapsmcp.tool_names(transport.call("tools/list", {}))
    places: int | None = None
    skipped: str | None = None
    if not has_key:
        skipped = mapsmcp.SKIP_NO_KEY
    elif not search:
        skipped = mapsmcp.SKIP_NO_SEARCH
    else:
        places = mapsmcp.count_places(transport.call("tools/call", mapsmcp.search_params()))
    return mapsmcp.CheckOutcome(
        server=str(server_info.get("name", "?")),
        protocol=negotiated or "?",
        tools=tools,
        missing=mapsmcp.missing_tools(tools),
        places=places,
        skipped=skipped,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-search", action="store_true", help="Handshake and tools/list only; never a billable tool call.")
    parser.add_argument("--endpoint", default=mapsmcp.MCP_ENDPOINT, help=argparse.SUPPRESS)  # tests only
    args = parser.parse_args(argv)
    api_key = os.environ.get(mapsmcp.API_KEY_ENV, "").strip() or None  # blank counts as unset
    transport = Transport(args.endpoint, api_key)
    try:
        outcome = run_check(transport, search=not args.no_search, has_key=api_key is not None)
    except mapsmcp.McpError as exc:
        print(f"FAIL: {exc}")
        return 1
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        print(f"FAIL: {type(exc).__name__} reaching the endpoint")
        return 1
    for line in outcome.lines():
        print(line)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
