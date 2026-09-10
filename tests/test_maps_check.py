"""Unit tests for headless/mapsmcp.py and scripts/maps_check.py (spec 010-google-maps-connector):
the JSON-RPC message shapes, both transport body shapes (plain JSON and SSE), the
value-free summaries, the transport's session-id and error handling with `urlopen`
stubbed, and the CLI's exit codes. No network, no key.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

import scripts.maps_check as maps_check
from headless import mapsmcp


# --- message shapes ----------------------------------------------------------------


def test_build_request_and_notification():
    request = json.loads(mapsmcp.build_request("tools/list", {}, 7))
    assert request == {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 7}
    notification = json.loads(mapsmcp.build_request("notifications/initialized", None, None))
    assert notification == {"jsonrpc": "2.0", "method": "notifications/initialized"}


def test_initialize_and_search_params():
    params = mapsmcp.initialize_params("0.0.10")
    assert params["protocolVersion"] == mapsmcp.PROTOCOL_VERSION
    assert params["clientInfo"] == {"name": mapsmcp.CLIENT_NAME, "version": "0.0.10"}
    search = mapsmcp.search_params()
    assert search["name"] == "search_places"
    assert search["arguments"] == {"textQuery": mapsmcp.PROBE_QUERY, "pageSize": 1}


def test_parse_response_plain_json_and_batch():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    assert mapsmcp.parse_response(body, "application/json; charset=UTF-8", 1) == {"ok": True}
    batch = json.dumps([{"jsonrpc": "2.0", "id": 2, "result": {"n": 2}}, {"jsonrpc": "2.0", "id": 3, "result": {"n": 3}}])
    assert mapsmcp.parse_response(batch, "application/json", 3) == {"n": 3}


def test_parse_response_sse_stream_picks_the_matching_id():
    stream = "\n".join([
        "event: message",
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}',
        "",
        "data: not json at all",  # a whole event that is not JSON is skipped
        "",
        'data: {"jsonrpc": "2.0", "id": 4, "result": {"tools": []}}',
        "",
    ])
    assert mapsmcp.parse_response(stream, "text/event-stream", 4) == {"tools": []}


def test_parse_response_sse_joins_continuation_lines_and_flattens_an_array_payload():
    continued = "\n".join([
        "event: message",
        'data: {"jsonrpc": "2.0", "id": 5,',
        'data:  "result": {"joined": true}}',
        "",
    ])
    assert mapsmcp.parse_response(continued, "text/event-stream", 5) == {"joined": True}
    array = 'data: [{"jsonrpc": "2.0", "id": 1, "result": {"a": 1}}, {"jsonrpc": "2.0", "id": 6, "result": {"b": 2}}]\n\n'
    assert mapsmcp.parse_response(array, "text/event-stream", 6) == {"b": 2}
    unterminated = 'data: {"jsonrpc": "2.0", "id": 7, "result": {"last": true}}'  # no trailing blank line
    assert mapsmcp.parse_response(unterminated, "text/event-stream", 7) == {"last": True}


def test_parse_response_errors():
    with pytest.raises(mapsmcp.McpError, match="JSON-RPC error -32602: bad params"):
        mapsmcp.parse_response(json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "bad params"}}), "application/json", 1)
    with pytest.raises(mapsmcp.McpError, match="no result for request 9"):
        mapsmcp.parse_response(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), "application/json", 9)
    with pytest.raises(mapsmcp.McpError, match="not JSON"):
        mapsmcp.parse_response("<html>", "text/html", 1)
    with pytest.raises(mapsmcp.McpError):
        mapsmcp.parse_response("", "application/json", 1)


def test_tool_names_and_missing_tools():
    listing = {"tools": [{"name": "search_places"}, {"name": "lookup_weather"}, {"noname": 1}, "junk"]}
    names = mapsmcp.tool_names(listing)
    assert names == ["search_places", "lookup_weather"]
    assert mapsmcp.missing_tools(names) == ["compute_routes"]
    assert mapsmcp.tool_names({}) == [] and mapsmcp.tool_names({"tools": "x"}) == []


def test_count_places_is_a_count_only():
    assert mapsmcp.count_places({"structuredContent": {"places": [{"name": "a"}, {"name": "b"}]}}) == 2
    assert mapsmcp.count_places({"structuredContent": {"places": []}}) == 0
    # answered, but no structured place list: the check never invents a count
    assert mapsmcp.count_places({"content": [{"type": "text", "text": "No places found"}]}) is None
    assert mapsmcp.count_places({"structuredContent": {}, "content": [{"type": "text", "text": "x"}]}) is None
    assert mapsmcp.count_places({"content": []}) == 0
    assert mapsmcp.count_places("nonsense") == 0
    with pytest.raises(mapsmcp.McpError):
        mapsmcp.count_places({"isError": True, "content": [{"type": "text", "text": "API key not valid"}]})


def test_outcome_lines_and_ok():
    tools = list(mapsmcp.EXPECTED_TOOLS)
    good = mapsmcp.CheckOutcome(server="S", protocol="2025-06-18", tools=tools, missing=[], places=1)
    assert good.ok and "search       PASS - search_places returned 1 result(s)" in good.lines()
    no_key = mapsmcp.CheckOutcome(server="S", protocol="p", tools=tools, missing=[], places=None, skipped=mapsmcp.SKIP_NO_KEY)
    assert no_key.ok and f"search       SKIP - {mapsmcp.API_KEY_ENV} is not set; the handshake needs no key, a tool call does" in no_key.lines()
    no_search = mapsmcp.CheckOutcome(server="S", protocol="p", tools=tools, missing=[], places=None, skipped=mapsmcp.SKIP_NO_SEARCH)
    assert no_search.ok and "search       SKIP - --no-search given; no billable tool call was made" in no_search.lines()
    unstructured = mapsmcp.CheckOutcome(server="S", protocol="p", tools=tools, missing=[], places=None)
    assert unstructured.ok
    assert "search       PASS - search_places answered (no structured place count in this response)" in unstructured.lines()
    missing = mapsmcp.CheckOutcome(server="S", protocol="p", tools=["search_places"], missing=["lookup_weather"], places=None, skipped=mapsmcp.SKIP_NO_KEY)
    assert not missing.ok and any("FAIL - missing lookup_weather" in line for line in missing.lines())
    empty = mapsmcp.CheckOutcome(server="S", protocol="p", tools=tools, missing=[], places=0)
    assert not empty.ok and "search       FAIL - search_places returned no result" in empty.lines()


# --- transport with urlopen stubbed -------------------------------------------------


class _Response:
    def __init__(self, status, body, headers):
        self.status = status
        self._body = body.encode("utf-8")
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _stub_server(monkeypatch, handler):
    """`handler(request) -> (status, body, headers)`; an HTTP status >= 400 becomes urllib's HTTPError."""
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request, timeout=0):
        seen.append(request)
        status, body, headers = handler(request)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", headers, io.BytesIO(body.encode("utf-8")))
        return _Response(status, body, headers)

    monkeypatch.setattr(maps_check.urllib.request, "urlopen", fake_urlopen)
    return seen


def _ok(request):
    message = json.loads(request.data)
    headers = {"Content-Type": "application/json", "Mcp-Session-Id": "sess-1"}
    if "id" not in message:
        return 202, "", headers
    if message["method"] == "initialize":
        result = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "StatelessServer"}}
    elif message["method"] == "tools/list":
        result = {"tools": [{"name": name} for name in mapsmcp.EXPECTED_TOOLS]}
    else:
        result = {"structuredContent": {"places": [{"id": "x"}]}}
    return 200, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), headers


def test_transport_sends_the_key_header_and_reuses_the_session_id(monkeypatch):
    seen = _stub_server(monkeypatch, _ok)
    transport = maps_check.Transport("https://example.invalid/mcp", "k-test")
    transport.call("initialize", mapsmcp.initialize_params("0.0.10"))
    transport.notify("notifications/initialized")
    transport.call("tools/list", {})
    first, second, third = seen
    assert first.get_header("X-goog-api-key") == "k-test"
    assert first.get_header("Mcp-session-id") is None
    assert second.get_header("Mcp-session-id") == "sess-1" and third.get_header("Mcp-session-id") == "sess-1"
    assert first.get_header("Accept") == "application/json, text/event-stream"


def test_transport_without_a_key_sends_no_key_header(monkeypatch):
    seen = _stub_server(monkeypatch, _ok)
    maps_check.Transport("https://example.invalid/mcp", None).call("tools/list", {})
    assert not any(name.lower() == "x-goog-api-key" for name in seen[0].headers)


def test_transport_sends_the_negotiated_protocol_version_after_initialize(monkeypatch):
    def negotiates(request):
        status, body, headers = _ok(request)
        message = json.loads(request.data)
        if message.get("method") == "initialize":
            body = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-03-26", "serverInfo": {"name": "S"}}})
        return status, body, headers

    seen = _stub_server(monkeypatch, negotiates)
    transport = maps_check.Transport("https://example.invalid/mcp", None)
    outcome = maps_check.run_check(transport, search=False, has_key=False)
    assert outcome.protocol == "2025-03-26"
    assert seen[0].get_header("Mcp-protocol-version") == mapsmcp.PROTOCOL_VERSION
    assert seen[1].get_header("Mcp-protocol-version") == "2025-03-26"
    assert seen[2].get_header("Mcp-protocol-version") == "2025-03-26"


def test_transport_never_echoes_the_key_from_a_gateway_error_page(monkeypatch):
    key = "k-DISTINCTIVE-SECRET-VALUE-9"
    page = f"<html><pre>POST /mcp HTTP/1.1\nX-Goog-Api-Key: {key}\n</pre></html>"

    def gateway(request):
        return 502, page, {"Content-Type": "text/html"}

    _stub_server(monkeypatch, gateway)
    with pytest.raises(mapsmcp.McpError) as excinfo:
        maps_check.Transport("https://example.invalid/mcp", key).call("tools/list", {})
    assert key not in str(excinfo.value)
    assert "non-JSON error body" in str(excinfo.value) and "not shown" in str(excinfo.value)


def test_transport_redacts_the_key_from_a_json_rpc_error_that_quotes_it(monkeypatch):
    key = "k-DISTINCTIVE-SECRET-VALUE-9"

    def quoting(request):
        message = json.loads(request.data)
        body = json.dumps({"jsonrpc": "2.0", "id": message.get("id", 0), "error": {"code": -32000, "message": f"bad key {key}"}})
        return 200, body, {"Content-Type": "application/json"}

    _stub_server(monkeypatch, quoting)
    with pytest.raises(mapsmcp.McpError) as excinfo:
        maps_check.Transport("https://example.invalid/mcp", key).call("tools/list", {})
    assert key not in str(excinfo.value) and "***" in str(excinfo.value)


def test_transport_survives_an_http_error_without_body_or_headers(monkeypatch):
    def bare(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 503, "unavailable", None, None)

    monkeypatch.setattr(maps_check.urllib.request, "urlopen", bare)
    with pytest.raises(mapsmcp.McpError, match="HTTP 503 on tools/list"):
        maps_check.Transport("https://example.invalid/mcp", "k-test").call("tools/list", {})


def test_transport_http_error_becomes_a_value_free_mcp_error(monkeypatch):
    def denied(request):
        return 403, json.dumps({"error": {"code": 403, "message": "API key not valid. Please pass a valid API key."}}), {"Content-Type": "application/json"}

    _stub_server(monkeypatch, denied)
    with pytest.raises(mapsmcp.McpError, match="HTTP 403 on tools/list: API key not valid"):
        maps_check.Transport("https://example.invalid/mcp", "k-secret-value").call("tools/list", {})


# --- the CLI -------------------------------------------------------------------------


def test_main_passes_with_a_key_and_one_search(monkeypatch, capsys):
    seen = _stub_server(monkeypatch, _ok)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, "k-test")
    assert maps_check.main([]) == 0
    out = capsys.readouterr().out
    assert "server       PASS - StatelessServer (protocol 2025-06-18)" in out
    assert "tools        PASS - search_places, lookup_weather, compute_routes" in out
    assert "search       PASS - search_places returned 1 result(s)" in out
    assert "k-test" not in out
    assert [json.loads(r.data)["method"] for r in seen] == ["initialize", "notifications/initialized", "tools/list", "tools/call"]


def test_main_skips_the_search_without_a_key_and_never_calls_a_tool(monkeypatch, capsys):
    seen = _stub_server(monkeypatch, _ok)
    monkeypatch.delenv(mapsmcp.API_KEY_ENV, raising=False)
    assert maps_check.main([]) == 0
    assert f"search       SKIP - {mapsmcp.API_KEY_ENV} is not set" in capsys.readouterr().out
    assert "tools/call" not in [json.loads(r.data)["method"] for r in seen]


def test_main_treats_a_blank_key_as_unset(monkeypatch, capsys):
    seen = _stub_server(monkeypatch, _ok)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, "   ")
    assert maps_check.main([]) == 0
    assert f"search       SKIP - {mapsmcp.API_KEY_ENV} is not set" in capsys.readouterr().out
    assert "tools/call" not in [json.loads(r.data)["method"] for r in seen]
    assert not any(name.lower() == "x-goog-api-key" for r in seen for name in r.headers)


def test_main_no_search_flag_never_calls_a_tool_even_with_a_key(monkeypatch, capsys):
    seen = _stub_server(monkeypatch, _ok)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, "k-test")
    assert maps_check.main(["--no-search"]) == 0
    out = capsys.readouterr().out
    assert "search       SKIP - --no-search given; no billable tool call was made" in out
    assert "is not set" not in out
    assert "tools/call" not in [json.loads(r.data)["method"] for r in seen]


def test_main_reports_an_unstructured_answer_without_inventing_a_count(monkeypatch, capsys):
    def text_only(request):
        message = json.loads(request.data)
        if message.get("method") == "tools/call":
            body = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": "No places found"}]}})
            return 200, body, {"Content-Type": "application/json"}
        return _ok(request)

    _stub_server(monkeypatch, text_only)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, "k-test")
    assert maps_check.main([]) == 0
    out = capsys.readouterr().out
    assert "search       PASS - search_places answered (no structured place count in this response)" in out
    assert "result(s)" not in out


def test_main_never_prints_the_key_when_a_gateway_page_echoes_it(monkeypatch, capsys):
    key = "k-DISTINCTIVE-SECRET-VALUE-9"

    def gateway(request):
        message = json.loads(request.data)
        if message.get("method") == "tools/call":
            return 502, f"<html>X-Goog-Api-Key: {key}</html>", {"Content-Type": "text/html"}
        return _ok(request)

    _stub_server(monkeypatch, gateway)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, key)
    assert maps_check.main([]) == 1
    out = capsys.readouterr().out
    assert key not in out and out.startswith("FAIL: HTTP 502 on tools/call")


def test_main_fails_on_a_missing_tool(monkeypatch, capsys):
    def partial(request):
        status, body, headers = _ok(request)
        message = json.loads(request.data)
        if message.get("method") == "tools/list":
            body = json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": [{"name": "search_places"}]}})
        return status, body, headers

    _stub_server(monkeypatch, partial)
    monkeypatch.delenv(mapsmcp.API_KEY_ENV, raising=False)
    assert maps_check.main([]) == 1
    assert "tools        FAIL - missing lookup_weather, compute_routes" in capsys.readouterr().out


def test_main_reports_a_transport_failure_value_free(monkeypatch, capsys):
    def offline(request, timeout=0):
        raise urllib.error.URLError("DISTINCTIVE-STACK-TRACE-SHOULD-NEVER-APPEAR")

    monkeypatch.setattr(maps_check.urllib.request, "urlopen", offline)
    monkeypatch.delenv(mapsmcp.API_KEY_ENV, raising=False)
    assert maps_check.main([]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL: URLError reaching the endpoint")
    assert "DISTINCTIVE" not in out


def test_main_reports_a_denied_key_without_echoing_it(monkeypatch, capsys):
    def denied(request):
        message = json.loads(request.data)
        if message.get("method") == "tools/call":
            return 403, json.dumps({"error": {"message": "API key not valid. Please pass a valid API key."}}), {"Content-Type": "application/json"}
        return _ok(request)

    _stub_server(monkeypatch, denied)
    monkeypatch.setenv(mapsmcp.API_KEY_ENV, "k-secret-value")
    assert maps_check.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL: HTTP 403 on tools/call: API key not valid" in out
    assert "k-secret-value" not in out
