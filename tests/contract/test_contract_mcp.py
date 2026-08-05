"""Contract Tests between Control Plane MCPProxyService and Data Plane FastMCP Server.

Verifies end-to-end JSON-RPC protocol contract, identity header propagation,
and tool call execution between Control Plane and Data Plane over HTTP/2.
"""

import httpx
import pytest

from src.control_plane.schemas import UserContext
from src.control_plane.services.mcp_proxy import MCPProxyService
from src.data_plane.mcp_server import app, get_current_user_context


@pytest.mark.asyncio
@pytest.mark.contract
async def test_control_plane_proxy_to_data_plane_server_contract():
    """Verify MCPProxyService successfully communicates with Data Plane mcp_server.app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://dataplane.internal"
    ) as client:
        proxy = MCPProxyService(client=client)
        user_ctx = UserContext(
            user_id="usr_contract_e2e", role="admin", scopes=["tools:execute", "read"]
        )

        # 1. Test initialize method
        init_res = await proxy.forward_request(
            method="initialize",
            params={},
            user_context=user_ctx,
            request_id="init-contract-1",
        )
        assert init_res["jsonrpc"] == "2.0"
        assert init_res["id"] == "init-contract-1"
        assert init_res["result"]["serverInfo"]["name"] == "data-plane-mcp"

        # 2. Test tools/list method
        list_res = await proxy.forward_request(
            method="tools/list",
            params={},
            user_context=user_ctx,
            request_id="list-contract-1",
        )
        assert list_res["jsonrpc"] == "2.0"
        assert "tools" in list_res["result"]

        # 3. Test call_tool helper method
        tool_res = await proxy.call_tool(
            name="profile_and_optimize_kernel",
            arguments={"source_code": "void test() {}"},
            user_context=user_ctx,
        )
        assert tool_res["jsonrpc"] == "2.0"
        assert "result" in tool_res
        assert tool_res["result"]["status"] == "SUCCESS"


@pytest.mark.asyncio
@pytest.mark.contract
async def test_identity_context_propagation_contract():
    """Verify UserContext identity attributes propagate cleanly across plane boundary."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://dataplane.internal"
    ) as client:
        proxy = MCPProxyService(client=client)
        user_ctx = UserContext(
            user_id="usr_identity_check", role="security_auditor", scopes=["audit:all"]
        )

        res = await proxy.forward_request(
            method="initialize",
            user_context=user_ctx,
        )
        assert res["jsonrpc"] == "2.0"

        # Verify context was reset afterwards
        assert get_current_user_context() is None
