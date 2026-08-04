"""Contract Tests for Model Context Protocol (MCP) JSON-RPC 2.0 HTTP Interface."""

import pytest


@pytest.mark.contract
def test_mcp_jsonrpc_initialize_handshake(test_client):
    """Test MCP JSON-RPC initialize protocol method over HTTP wire.

    Asserts protocolVersion '2024-11-05', capabilities, and serverInfo schema.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {},
        "id": "init-001",
    }
    response = test_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200

    res_data = response.json()
    assert res_data.get("jsonrpc") == "2.0"
    assert res_data.get("id") == "init-001"

    result = res_data.get("result", {})
    assert result.get("protocolVersion") == "2024-11-05"
    assert "capabilities" in result
    assert result.get("serverInfo", {}).get("name") == "mvcp-gke-gateway"


@pytest.mark.contract
def test_mcp_jsonrpc_tools_list(test_client):
    """Test MCP JSON-RPC tools/list method over HTTP wire.

    Asserts tools array containing valid FastMCP tool schema objects.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": "list-001",
    }
    response = test_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200

    res_data = response.json()
    assert res_data.get("jsonrpc") == "2.0"
    assert res_data.get("id") == "list-001"

    tools = res_data.get("result", {}).get("tools", [])
    assert isinstance(tools, list)
    assert len(tools) > 0

    tool_names = [t.get("name") for t in tools]
    assert any(name in tool_names for name in ["optimize_kernel", "profile_and_optimize_kernel"])


@pytest.mark.contract
def test_mcp_jsonrpc_tools_call_execution(test_client):
    """Test MCP JSON-RPC tools/call protocol method for sandboxed execution.

    Asserts result payload contains valid content array with text execution output.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void matmul() {}"},
        },
        "id": "call-001",
    }
    response = test_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200

    res_data = response.json()
    assert res_data.get("jsonrpc") == "2.0"
    assert res_data.get("id") == "call-001"

    result = res_data.get("result", {})
    assert "content" in result
    content = result.get("content", [])
    assert len(content) > 0
    assert content[0].get("type") == "text"


@pytest.mark.contract
def test_mcp_jsonrpc_invalid_method_error(test_client):
    """Test MCP JSON-RPC error response for unsupported methods.

    Asserts JSON-RPC 2.0 error object with code -32601 (Method not found).
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "non_existent_method",
        "params": {},
        "id": "err-001",
    }
    response = test_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200  # JSON-RPC spec requires 200 HTTP status with error payload

    res_data = response.json()
    assert res_data.get("jsonrpc") == "2.0"
    assert res_data.get("id") == "err-001"
    assert "error" in res_data
    assert res_data["error"].get("code") == -32601


@pytest.mark.contract
def test_mcp_registry_workspace_slicing(test_client):
    """Test GET /api/v1/registry/tools with workspace context header."""
    response = test_client.get(
        "/api/v1/registry/tools",
        headers={"x-workspace-context": "cloud-ai"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert "tools" in res_data
    assert res_data.get("tool_count", 0) > 0


@pytest.mark.contract
def test_data_plane_sandbox_execution_endpoint(test_client):
    """Test POST /api/v1/sandbox/execute endpoint for gVisor execution status."""
    payload = {"script": "result = 1 + 1", "timeout_seconds": 10}
    response = test_client.post("/api/v1/sandbox/execute", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data.get("status") == "SUCCESS"
    assert res_data.get("exit_code") == 0
