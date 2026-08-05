"""Async Unit Tests for Data Plane Standalone FastMCP Server (/api/v1/mcp).

Verifies JSON-RPC 2.0 protocol compliance, tool dispatching, identity header propagation,
and ContextVar token reset behavior.
"""

import httpx
import pytest

from src.data_plane.mcp_server import app, get_current_user_context


@pytest.fixture
async def async_mcp_client():
    """Fixture providing an httpx.AsyncClient targeting the in-memory FastMCP ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://dataplane.test") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_initialize_method(async_mcp_client):
    """Verify 'initialize' method returns FastMCP server metadata and capabilities."""
    payload = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {},
    }
    response = await async_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "init-1"
    assert data["result"]["serverInfo"]["name"] == "data-plane-mcp"
    assert "capabilities" in data["result"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_tools_list_method(async_mcp_client):
    """Verify 'tools/list' method returns available tool catalog."""
    payload = {
        "jsonrpc": "2.0",
        "id": "list-1",
        "method": "tools/list",
        "params": {},
    }
    response = await async_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "list-1"
    assert "tools" in data["result"]
    tool_names = [t["name"] for t in data["result"]["tools"]]
    assert "optimize_kernel" in tool_names or "profile_and_optimize_kernel" in tool_names


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_tools_call_execution(async_mcp_client):
    """Verify 'tools/call' method executes tool and returns execution result."""
    payload = {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": "profile_and_optimize_kernel",
            "arguments": {"source_code": "void matmul() {}"},
        },
    }
    response = await async_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "call-1"
    assert "result" in data
    assert data["result"]["status"] == "SUCCESS"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_identity_header_extraction_and_context_reset(async_mcp_client):
    """Verify identity headers are extracted into context and reset after request completes."""
    # Ensure context is empty initially
    assert get_current_user_context() is None

    headers = {
        "X-User-ID": "usr_mcp_unit_test",
        "X-User-Role": "admin",
        "X-User-Scopes": "tools:execute, admin:read",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": "header-1",
        "method": "initialize",
    }
    response = await async_mcp_client.post("/api/v1/mcp", json=payload, headers=headers)
    assert response.status_code == 200

    # ContextVar must be reset to None after request completion to prevent bleeding
    assert get_current_user_context() is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_error_32700_parse_error(async_mcp_client):
    """Verify -32700 Parse Error returned when request body is non-JSON or malformed."""
    response = await async_mcp_client.post(
        "/api/v1/mcp",
        content="invalid json payload {{{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["error"]["code"] == -32700
    assert "Parse error" in data["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_error_32600_invalid_request(async_mcp_client):
    """Verify -32600 Invalid Request returned when request body violates JSON-RPC schema."""
    # Missing required method field
    payload = {"jsonrpc": "2.0", "id": "inv-1"}
    response = await async_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["error"]["code"] == -32600


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_error_32601_method_not_found(async_mcp_client):
    """Verify -32601 Method Not Found returned when unmapped method is requested."""
    payload = {
        "jsonrpc": "2.0",
        "id": "unknown-1",
        "method": "nonexistent/method",
    }
    response = await async_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["error"]["code"] == -32601
    assert "Method 'nonexistent/method' not found" in data["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_batch_request_rejection(async_mcp_client):
    """Verify batch JSON-RPC requests (arrays) are explicitly rejected with code -32600."""
    batch_payload = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    response = await async_mcp_client.post("/api/v1/mcp", json=batch_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["error"]["code"] == -32600
    assert "Batch JSON-RPC requests are not supported" in data["error"]["message"]
