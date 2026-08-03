"""Fast E2E Smoke Test Suite.

Executes lightweight HTTP and RPC assertions in sub-second runtime via api_client fixture.
"""

import pytest


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_gateway_health(api_client):
    """Verify gateway readiness health endpoint."""
    res = await api_client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_mcp_json_rpc_loops(api_client):
    """Verify MCP tools/list, resources/list, and tools/call JSON-RPC frames."""
    req_tools_list = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    req_res_list = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "resources/list",
        "params": {},
    }
    req_tool_call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "optimize_kernel",
            "arguments": {"code": "void smoke_kernel() {}"},
        },
    }

    r1 = await api_client.post("/api/v1/mcp", json=req_tools_list)
    assert r1.status_code == 200
    assert "tools" in r1.json()["result"]

    r2 = await api_client.post("/api/v1/mcp", json=req_res_list)
    assert r2.status_code == 200
    assert "resources" in r2.json()["result"]

    r3 = await api_client.post("/api/v1/mcp", json=req_tool_call)
    assert r3.status_code == 200
    assert "result" in r3.json()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_registry_tool_dispatcher(api_client):
    """Verify registry tool execution via /api/v1/registry/call."""
    payload = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void smoke_dispatch() {}"},
    }
    res = await api_client.post("/api/v1/registry/call", json=payload)
    assert res.status_code == 200
    assert res.json()["result"]["status"] == "SUCCESS"
