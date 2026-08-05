"""Unit tests for Control Plane MCP Proxy Service and Client Injection."""

import httpx
import pytest

from src.control_plane.dependencies import UserContext
from src.control_plane.services.mcp_proxy import MCPProxyService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_proxy_successful_call_tool():
    """Verify call_tool formats JSON-RPC 2.0 payload and returns Data Plane response."""
    received_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "req-001",
                "result": {"status": "SUCCESS", "output": "Kernel optimized"},
            },
        )

    client = httpx.AsyncClient(
        base_url="http://mcp-data-plane.internal:8000",
        transport=httpx.MockTransport(mock_handler),
    )
    service = MCPProxyService(client=client)

    result = await service.call_tool(
        name="optimize_kernel", arguments={"code": "void kernel() {}"}
    )

    assert result["jsonrpc"] == "2.0"
    assert result["result"]["status"] == "SUCCESS"
    assert len(received_requests) == 1
    assert received_requests[0].url == "http://mcp-data-plane.internal:8000/api/v1/mcp"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_proxy_identity_header_propagation():
    """Verify zero-trust UserContext headers are injected into outbound requests."""
    captured_headers = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": "OK"})

    client = httpx.AsyncClient(
        base_url="http://mcp-data-plane.internal:8000",
        transport=httpx.MockTransport(mock_handler),
    )
    service = MCPProxyService(client=client)

    user_ctx = UserContext(
        user_id="usr_test_123",
        role="admin",
        scopes=["llm:proxy", "tools:register"],
    )

    await service.call_tool("test_tool", user_context=user_ctx)

    assert captured_headers.get("x-user-id") == "usr_test_123"
    assert captured_headers.get("x-user-role") == "admin"
    assert captured_headers.get("x-user-scopes") == "llm:proxy, tools:register"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_proxy_timeout_error_mapping():
    """Verify httpx.TimeoutException maps to standard JSON-RPC -32000 error."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection to Data Plane timed out")

    client = httpx.AsyncClient(
        base_url="http://mcp-data-plane.internal:8000",
        transport=httpx.MockTransport(mock_handler),
    )
    service = MCPProxyService(client=client)

    res = await service.call_tool("timeout_tool")

    assert res.get("jsonrpc") == "2.0"
    assert "error" in res
    assert res["error"]["code"] == -32000
    assert "timed out" in res["error"]["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_proxy_http_error_mapping():
    """Verify HTTP error status code maps to standard JSON-RPC -32603 error."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error in Data Plane")

    client = httpx.AsyncClient(
        base_url="http://mcp-data-plane.internal:8000",
        transport=httpx.MockTransport(mock_handler),
    )
    service = MCPProxyService(client=client)

    res = await service.call_tool("failing_tool")

    assert res.get("jsonrpc") == "2.0"
    assert "error" in res
    assert res["error"]["code"] == -32603
    assert "500" in res["error"]["message"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mcp_proxy_close():
    """Verify close method correctly closes injected client."""
    external_client = httpx.AsyncClient(base_url="http://mcp-data-plane.internal:8000")
    injected_service = MCPProxyService(client=external_client)
    await injected_service.close()
    assert external_client.is_closed
