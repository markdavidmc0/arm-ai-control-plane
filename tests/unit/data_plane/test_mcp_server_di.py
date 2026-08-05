"""Async Unit Tests for Data Plane FastMCP Dependency Injection.

Verifies route handling at /api/v1/mcp using FastAPI dependency_overrides,
ensuring execution delegates through injected BaseToolDispatcher and DataPlaneSandboxRunner
without invoking actual binaries or module-level singletons.
"""

from typing import Any

import httpx
import pytest
from fastapi import Request

from src.data_plane.dependencies import get_sandbox_runner, get_tool_dispatcher
from src.data_plane.mcp_server import app
from src.data_plane.schemas import DataPlaneUserContext
from src.data_plane.worker import BaseToolDispatcher

DEFAULT_HEADERS = {
    "X-User-ID": "usr_di_unit_test",
    "X-User-Role": "developer",
    "X-User-Scopes": "tools:execute",
    "MCP-Protocol-Version": "2026-07-28",
}


class DummyTestRunner:
    """Mock implementation of DataPlaneSandboxRunner for testing."""

    async def execute_payload(
        self,
        code_snippet: str,
        repl_state: dict[str, Any] | None = None,
        tool_bindings: dict[str, Any] | None = None,
        user_context: DataPlaneUserContext | None = None,
    ) -> dict[str, Any]:
        """Mock payload execution."""
        return {"status": "success", "result": "mock_runner_ok"}


class DummyTestDispatcher(BaseToolDispatcher):
    """Mock implementation of BaseToolDispatcher for DI override verification."""

    def __init__(self) -> None:
        self.dispatched_calls: list[tuple[str, dict[str, Any], DataPlaneUserContext | None]] = []

    async def read_catalog(self) -> list[dict[str, Any]]:
        """Reads mock tool catalog."""
        return [
            {
                "name": "dummy_mock_tool",
                "description": "Mock tool for testing DI overrides",
                "inputSchema": {"type": "object"},
            }
        ]

    async def dispatch_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        user_context: DataPlaneUserContext | None = None,
    ) -> dict[str, Any]:
        """Dispatches mock tool call and records invocation arguments."""
        args = arguments or {}
        self.dispatched_calls.append((tool_name, args, user_context))
        return {
            "jsonrpc": "2.0",
            "result": {
                "tool_name": tool_name,
                "status": "SUCCESS",
                "output": {"mock_executed": True, "tool_name": tool_name},
            },
        }


@pytest.fixture
def dummy_dispatcher() -> DummyTestDispatcher:
    """Fixture providing a DummyTestDispatcher instance."""
    return DummyTestDispatcher()


@pytest.fixture
async def async_di_mcp_client(dummy_dispatcher: DummyTestDispatcher):
    """Fixture configuring app.dependency_overrides and yielding AsyncClient."""
    app.dependency_overrides[get_tool_dispatcher] = lambda: dummy_dispatcher
    app.dependency_overrides[get_sandbox_runner] = lambda: DummyTestRunner()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://dataplane.test", headers=DEFAULT_HEADERS
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_sandbox_runner_override(async_di_mcp_client):
    """Verify DataPlaneSandboxRunner dependency override works as expected."""
    runner = get_sandbox_runner(Request({"type": "http", "app": app}))
    assert runner is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_tools_list_uses_injected_dispatcher(async_di_mcp_client, dummy_dispatcher):
    """Verify tools/list uses the injected BaseToolDispatcher dependency."""
    payload = {
        "jsonrpc": "2.0",
        "id": "di-list-1",
        "method": "tools/list",
        "params": {},
    }
    response = await async_di_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "di-list-1"
    assert "tools" in data["result"]
    assert len(data["result"]["tools"]) == 1
    assert data["result"]["tools"][0]["name"] == "dummy_mock_tool"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_mcp_tools_call_uses_injected_dispatcher(async_di_mcp_client, dummy_dispatcher):
    """Verify tools/call routes through the injected BaseToolDispatcher dependency."""
    payload = {
        "jsonrpc": "2.0",
        "id": "di-call-1",
        "method": "tools/call",
        "params": {
            "name": "dummy_mock_tool",
            "arguments": {"key": "val"},
        },
    }
    response = await async_di_mcp_client.post("/api/v1/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "di-call-1"
    assert data["result"]["output"]["mock_executed"] is True

    # Assert DummyTestDispatcher recorded call with propagated user_context
    assert len(dummy_dispatcher.dispatched_calls) == 1
    tool_name, args, user_ctx = dummy_dispatcher.dispatched_calls[0]
    assert tool_name == "dummy_mock_tool"
    assert args == {"key": "val"}
    assert user_ctx is not None
    assert user_ctx.user_id == "usr_di_unit_test"
