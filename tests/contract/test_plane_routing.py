"""Control Plane to Data Plane Network Wire Contract Tests."""

import httpx
import pytest

from src.control_plane.schemas import UserContext
from src.control_plane.services.mcp_proxy import MCPProxyService


@pytest.mark.asyncio
@pytest.mark.contract
async def test_control_to_data_plane_header_and_payload_contract():
    """Verify that MCPProxyService fulfills identity header and JSON-RPC wire contract."""
    captured_request: httpx.Request | None = None

    def mock_data_plane_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 100,
                "result": {"status": "success", "tools": []},
            },
        )

    # Instantiate HTTP client with base_url and mock transport
    async with httpx.AsyncClient(
        base_url="http://dataplane.internal",
        transport=httpx.MockTransport(mock_data_plane_handler),
    ) as client:
        proxy = MCPProxyService(client=client)
        ctx = UserContext(user_id="usr_contract_test", role="admin", scopes=["tools:execute"])

        response = await proxy.forward_request(
            method="tools/list",
            params={},
            user_context=ctx,
            request_id=100,
        )

    # 1. Assert Identity Header Propagation Contract
    assert captured_request is not None
    assert captured_request.headers["X-User-ID"] == "usr_contract_test"
    assert captured_request.headers["X-User-Role"] == "admin"
    assert captured_request.headers["X-User-Scopes"] == "tools:execute"

    # 2. Assert JSON-RPC 2.0 Wire Contract
    body = captured_request.read().decode("utf-8")
    assert '"jsonrpc":' in body or '"jsonrpc": ' in body
    assert '"method":' in body or '"method": ' in body
    assert response["result"]["status"] == "success"
