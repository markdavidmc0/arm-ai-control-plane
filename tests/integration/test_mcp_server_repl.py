"""Integration Tests for End-to-End HTTP JSON-RPC REPL Execution at /api/v1/mcp.

Verifies process timeout handling (-32603) and dynamic sandbox execution
without hardcoded mock fallbacks or PMU counters.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.data_plane.mcp_server import app

DEFAULT_HEADERS = {
    "X-User-ID": "usr_mcp_repl_integration",
    "X-User-Role": "developer",
    "X-User-Scopes": "tools:execute",
    "MCP-Protocol-Version": "2026-07-28",
}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_endpoint_timeout_handling():
    """Verify POST /api/v1/mcp with infinite loop returns HTTP 200 with JSON-RPC error -32603."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://dataplane.test", headers=DEFAULT_HEADERS
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "timeout-1",
            "method": "tools/call",
            "params": {
                "name": "repl_execute",
                "arguments": {"code": "while True:\n    pass"},
            },
        }

        response = await client.post("/api/v1/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == -32603
        assert "Execution timed out" in data["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_mcp_endpoint_no_mock_bypass():
    """Verify dynamic execution returns no synthetic PMU counters or mock strings."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://dataplane.test", headers=DEFAULT_HEADERS
    ) as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "eval-1",
            "method": "tools/call",
            "params": {
                "name": "repl_execute",
                "arguments": {"code": "result = 1 + 1"},
            },
        }

        response = await client.post("/api/v1/mcp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert "Arm Neoverse N2" not in response.text
        assert "arm_pmu_counters" not in response.text
