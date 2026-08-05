"""MCP 2026-07-28 Protocol Alignment & Contract Compliance Test Suite."""

from fastapi.testclient import TestClient

from src.data_plane.mcp_server import app

client = TestClient(app)

HEADERS = {
    "X-User-ID": "usr_test_mcp_001",
    "X-User-Role": "developer",
    "X-User-Scopes": "tools:execute",
    "MCP-Protocol-Version": "2026-07-28",
}

# --- Discovery & Initialization ---


def test_mcp_2026_07_28_server_discover():
    """Verify stateless 'server/discover' method and _meta handling."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req-001",
        "method": "server/discover",
        "params": {},
        "_meta": {"client": "test-suite", "capabilities": {}},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "req-001"
    assert "protocolVersions" in data["result"]
    assert "2026-07-28" in data["result"]["protocolVersions"]
    assert "capabilities" in data["result"]


def test_legacy_initialize_fallback():
    """Verify legacy 'initialize' method remains accessible as a fallback."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25"},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert "capabilities" in data["result"]


# --- Core MCP Primitives ---


def test_mcp_tools_list_contract():
    """Verify tools/list returns standard MCP tool schema format."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req-tools-01",
        "method": "tools/list",
        "params": {},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert "tools" in data["result"]
    assert isinstance(data["result"]["tools"], list)


def test_mcp_tools_call_schema():
    """Verify tools/call parameters acceptance."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req-exec-01",
        "method": "tools/call",
        "params": {
            "name": "profile_and_optimize_kernel",
            "arguments": {"source_code": "void test() {}"},
        },
        "_meta": {"progressToken": 1},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "req-exec-01"
    assert ("result" in data) or ("error" in data)


# --- Error Handling & Specification Edge Cases ---


def test_jsonrpc_method_not_found_error():
    """Verify unknown RPC methods return code -32601."""
    payload = {
        "jsonrpc": "2.0",
        "id": "err-001",
        "method": "unknown/invalidMethodName",
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "err-001"
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_jsonrpc_invalid_params_error():
    """Verify tools/call missing required tool name returns code -32602."""
    payload = {
        "jsonrpc": "2.0",
        "id": "err-002",
        "method": "tools/call",
        "params": {},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32602


def test_jsonrpc_notification_omits_response_body():
    """Verify notifications (requests without an id) do not expect a result body."""
    payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    response = client.post("/api/v1/mcp", json=payload, headers=HEADERS)
    assert response.status_code in (200, 204)
    if response.status_code == 200 and response.content:
        data = response.json()
        assert data.get("id") is None


def test_disallow_jsonrpc_batching():
    """Verify MCP spec restriction against batch array payloads."""
    batch_payload = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
        {"jsonrpc": "2.0", "id": 2, "method": "server/discover"},
    ]
    response = client.post("/api/v1/mcp", json=batch_payload, headers=HEADERS)
    assert response.status_code in (400, 422)


def test_missing_zero_trust_headers():
    """Verify execution is rejected if control-plane headers are missing."""
    payload = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "server/discover",
    }
    response = client.post("/api/v1/mcp", json=payload)
    assert response.status_code in (400, 401, 403, 422)


def test_unsupported_protocol_version_fallback():
    """Verify handling of legacy or unrecognized MCP protocol versions."""
    custom_headers = {**HEADERS, "MCP-Protocol-Version": "1999-01-01"}
    payload = {
        "jsonrpc": "2.0",
        "id": "ver-001",
        "method": "server/discover",
    }
    response = client.post("/api/v1/mcp", json=payload, headers=custom_headers)
    assert response.status_code == 200
    data = response.json()
    assert "2026-07-28" in data["result"]["protocolVersions"]
