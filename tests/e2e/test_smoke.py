"""Fast E2E Smoke Test Suite.

Executes lightweight HTTP and RPC assertions in < 10s using in-memory TestClient or active cluster.
"""

import httpx
import pytest

from tests.e2e.conftest import E2E_TARGET, GATEWAY_BASE_URL


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_gateway_health(test_client):
    """Verify gateway readiness health endpoint."""
    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=5.0) as client:
            res = await client.get("/api/v1/health")
            assert res.status_code == 200
            assert res.json()["status"] == "healthy"
    else:
        res = test_client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_mcp_json_rpc_loops(test_client):
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

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=5.0) as client:
            r1 = await client.post("/api/v1/mcp", json=req_tools_list)
            assert r1.status_code == 200 and "tools" in r1.json()["result"]

            r2 = await client.post("/api/v1/mcp", json=req_res_list)
            assert r2.status_code == 200 and "resources" in r2.json()["result"]

            r3 = await client.post("/api/v1/mcp", json=req_tool_call)
            assert r3.status_code == 200 and "result" in r3.json()
    else:
        r1 = test_client.post("/api/v1/mcp", json=req_tools_list)
        assert r1.status_code == 200 and "tools" in r1.json()["result"]

        r2 = test_client.post("/api/v1/mcp", json=req_res_list)
        assert r2.status_code == 200 and "resources" in r2.json()["result"]

        r3 = test_client.post("/api/v1/mcp", json=req_tool_call)
        assert r3.status_code == 200 and "result" in r3.json()


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_registry_tool_dispatcher(test_client):
    """Verify registry tool execution via /api/v1/registry/call."""
    payload = {
        "name": "profile_and_optimize_kernel",
        "arguments": {"source_code": "void smoke_dispatch() {}"},
    }

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        async with httpx.AsyncClient(base_url=GATEWAY_BASE_URL, timeout=5.0) as client:
            res = await client.post("/api/v1/registry/call", json=payload)
            assert res.status_code == 200
            assert res.json()["result"]["status"] == "SUCCESS"
    else:
        res = test_client.post("/api/v1/registry/call", json=payload)
        assert res.status_code == 200
        assert res.json()["result"]["status"] == "SUCCESS"
